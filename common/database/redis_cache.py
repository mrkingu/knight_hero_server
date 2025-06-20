"""
Redis缓存层实现
包含连接池管理、原子操作、分布式锁等功能
作者: lx
日期: 2025-06-18
"""
import asyncio
import random
import hashlib
import time
import json
import logging
from typing import Any, Optional, Dict, List, Union, Set, Tuple
from contextlib import asynccontextmanager
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .distributed_lock import DistributedLock, distributed_lock

logger = logging.getLogger(__name__)


class BloomFilter:
    """布隆过滤器实现，用于防止缓存穿透"""
    
    def __init__(self, redis_client, key_prefix: str = "bloom", 
                 expected_items: int = 1000000, false_positive_rate: float = 0.01):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.expected_items = expected_items
        self.false_positive_rate = false_positive_rate
        
        # 计算最优的位数组大小和哈希函数数量
        self.bit_size = self._optimal_bit_size()
        self.hash_count = self._optimal_hash_count()
        
        # Lua脚本用于原子操作
        self.add_script = """
            local key = KEYS[1]
            local bit_size = tonumber(ARGV[1])
            local hash_count = tonumber(ARGV[2])
            local item = ARGV[3]
            
            for i = 1, hash_count do
                local hash = redis.call('EVALSHA', ARGV[4], 0, item, i) % bit_size
                redis.call('SETBIT', key, hash, 1)
            end
            return 1
        """
        
        self.check_script = """
            local key = KEYS[1]
            local bit_size = tonumber(ARGV[1])
            local hash_count = tonumber(ARGV[2])
            local item = ARGV[3]
            
            for i = 1, hash_count do
                local hash = redis.call('EVALSHA', ARGV[4], 0, item, i) % bit_size
                if redis.call('GETBIT', key, hash) == 0 then
                    return 0
                end
            end
            return 1
        """
    
    def _optimal_bit_size(self) -> int:
        """计算最优位数组大小"""
        import math
        return int(-self.expected_items * math.log(self.false_positive_rate) / (math.log(2) ** 2))
    
    def _optimal_hash_count(self) -> int:
        """计算最优哈希函数数量"""
        import math
        return int(self.bit_size * math.log(2) / self.expected_items)
    
    async def add(self, item: str, key_suffix: str = "default") -> None:
        """添加元素到布隆过滤器"""
        key = f"{self.key_prefix}:{key_suffix}"
        await self.redis.eval(
            self.add_script,
            1,
            key,
            self.bit_size,
            self.hash_count,
            item,
            self._hash_function_sha
        )
    
    async def contains(self, item: str, key_suffix: str = "default") -> bool:
        """检查元素是否可能存在"""
        key = f"{self.key_prefix}:{key_suffix}"
        result = await self.redis.eval(
            self.check_script,
            1,
            key,
            self.bit_size,
            self.hash_count,
            item,
            self._hash_function_sha
        )
        return bool(result)
    
    @property
    def _hash_function_sha(self) -> str:
        """哈希函数的SHA值"""
        hash_func = """
            local item = ARGV[1]
            local seed = tonumber(ARGV[2])
            return redis.sha1hex(item .. seed)
        """
        return hashlib.sha1(hash_func.encode()).hexdigest()


class RedisCache:
    """Redis缓存层"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        min_connections: int = 20,
        max_connections: int = 100,
        retry_on_timeout: bool = True,
        socket_keepalive: bool = True,
        socket_keepalive_options: Optional[Dict] = None
    ):
        """
        初始化Redis缓存
        
        Args:
            host: Redis主机地址
            port: Redis端口
            db: 数据库编号
            password: 密码
            min_connections: 最小连接数
            max_connections: 最大连接数
            retry_on_timeout: 超时重试
            socket_keepalive: 保持连接
            socket_keepalive_options: 连接保持选项
        """
        # 创建连接池
        self.pool = ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            min_connections=min_connections,
            max_connections=max_connections,
            retry_on_timeout=retry_on_timeout,
            socket_keepalive=socket_keepalive,
            socket_keepalive_options=socket_keepalive_options or {}
        )
        
        self.redis = redis.Redis(connection_pool=self.pool)
        self.bloom_filter = BloomFilter(self.redis)
        
        # TTL配置
        self.ttl_config = {
            "player": 300,      # 玩家数据5分钟
            "config": 3600,     # 配置数据1小时
            "ranking": 60,      # 排行榜1分钟
            "session": 1800,    # 会话30分钟
        }
        
        # 热点数据配置(永不过期)
        self.hot_keys = {
            "config:*",         # 所有配置
            "ranking:top100",   # 前100排行榜
        }
        
        # 预热数据模式
        self.preheat_patterns = [
            "player:*:info",    # 玩家基础信息
            "config:item:*",    # 道具配置
        ]
        
        # 统计信息
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "pipeline_ops": 0,
            "lua_script_ops": 0
        }
        
        # Lua脚本SHA缓存
        self.script_shas: Dict[str, str] = {}
    
    async def connect(self) -> None:
        """建立连接"""
        try:
            await self.redis.ping()
            logger.info("Redis连接成功")
            
            # 预加载Lua脚本
            await self._preload_lua_scripts()
            
        except Exception as e:
            logger.error(f"Redis连接失败: {e}")
            raise
    
    async def disconnect(self) -> None:
        """断开连接"""
        await self.redis.close()
        await self.pool.disconnect()
        logger.info("Redis连接已断开")
    
    async def _preload_lua_scripts(self) -> None:
        """预加载Lua脚本"""
        scripts = {
            # 原子增量操作脚本
            "atomic_incr": """
                local key = KEYS[1]
                local amount = tonumber(ARGV[1])
                local min_val = tonumber(ARGV[2])
                local max_val = tonumber(ARGV[3])
                local ttl = tonumber(ARGV[4])
                
                local current = redis.call('GET', key)
                if current == false then
                    current = 0
                else
                    current = tonumber(current)
                end
                
                local new_val = current + amount
                if new_val < min_val or new_val > max_val then
                    return {0, current, 'value_out_of_bounds'}
                end
                
                redis.call('SET', key, new_val)
                if ttl > 0 then
                    redis.call('EXPIRE', key, ttl)
                end
                
                return {1, new_val, 'success'}
            """,
            
            # 批量操作脚本
            "batch_operations": """
                local results = {}
                local key_count = tonumber(ARGV[1])
                
                for i = 1, key_count do
                    local key = KEYS[i]
                    local operation = ARGV[i + 1]
                    local value = ARGV[i + key_count + 1]
                    
                    if operation == 'SET' then
                        redis.call('SET', key, value)
                        table.insert(results, 'OK')
                    elseif operation == 'GET' then
                        local val = redis.call('GET', key)
                        table.insert(results, val or '')
                    elseif operation == 'INCR' then
                        local val = redis.call('INCRBY', key, tonumber(value))
                        table.insert(results, val)
                    elseif operation == 'DEL' then
                        local val = redis.call('DEL', key)
                        table.insert(results, val)
                    end
                end
                
                return results
            """,
            
            # 防缓存雪崩脚本(随机TTL)
            "set_with_random_ttl": """
                local key = KEYS[1]
                local value = ARGV[1]
                local base_ttl = tonumber(ARGV[2])
                local variance = tonumber(ARGV[3])
                
                local random_ttl = base_ttl + math.random(-variance, variance)
                redis.call('SETEX', key, random_ttl, value)
                
                return random_ttl
            """
        }
        
        for name, script in scripts.items():
            sha = await self.redis.script_load(script)
            self.script_shas[name] = sha
            logger.debug(f"加载Lua脚本: {name} -> {sha}")
    
    def _get_ttl(self, key_type: str) -> int:
        """获取TTL并添加随机化"""
        base_ttl = self.ttl_config.get(key_type, 300)
        # 添加±20%的随机化
        variance = int(base_ttl * 0.2)
        return base_ttl + random.randint(-variance, variance)
    
    def _is_hot_key(self, key: str) -> bool:
        """检查是否为热点键"""
        import fnmatch
        return any(fnmatch.fnmatch(key, pattern) for pattern in self.hot_keys)
    
    async def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
        try:
            value = await self.redis.get(key)
            if value is not None:
                self.stats["hits"] += 1
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value.decode() if isinstance(value, bytes) else value
            else:
                self.stats["misses"] += 1
                return default
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, {e}")
            return default
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        key_type: str = "default"
    ) -> bool:
        """设置缓存值"""
        try:
            # 序列化值
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value, ensure_ascii=False)
            else:
                serialized_value = str(value)
            
            # 确定TTL
            if self._is_hot_key(key):
                # 热点数据不设置过期时间
                await self.redis.set(key, serialized_value)
            else:
                final_ttl = ttl or self._get_ttl(key_type)
                await self.redis.setex(key, final_ttl, serialized_value)
            
            self.stats["sets"] += 1
            
            # 添加到布隆过滤器
            await self.bloom_filter.add(key, key_type)
            
            return True
            
        except Exception as e:
            logger.error(f"设置缓存失败: {key}, {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            result = await self.redis.delete(key)
            self.stats["deletes"] += 1
            return bool(result)
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error(f"检查键存在性失败: {key}, {e}")
            return False
    
    async def atomic_increment(
        self,
        key: str,
        amount: int = 1,
        min_value: int = 0,
        max_value: int = 999999999,
        ttl: int = 0
    ) -> Tuple[bool, int, str]:
        """
        原子增量操作
        
        Returns:
            (success, new_value, message)
        """
        try:
            result = await self.redis.evalsha(
                self.script_shas["atomic_incr"],
                1,
                key,
                amount,
                min_value,
                max_value,
                ttl
            )
            
            self.stats["lua_script_ops"] += 1
            return bool(result[0]), int(result[1]), result[2]
            
        except Exception as e:
            logger.error(f"原子增量操作失败: {key}, {e}")
            return False, 0, str(e)
    
    async def pipeline_operations(self, operations: List[Dict[str, Any]]) -> List[Any]:
        """
        管道批量操作
        
        Args:
            operations: 操作列表，格式: [{"cmd": "set", "key": "k1", "value": "v1"}, ...]
        """
        try:
            async with self.redis.pipeline() as pipe:
                for op in operations:
                    cmd = op["cmd"].lower()
                    if cmd == "get":
                        pipe.get(op["key"])
                    elif cmd == "set":
                        pipe.set(op["key"], op["value"], ex=op.get("ttl"))
                    elif cmd == "delete":
                        pipe.delete(op["key"])
                    elif cmd == "incr":
                        pipe.incrby(op["key"], op.get("amount", 1))
                    elif cmd == "exists":
                        pipe.exists(op["key"])
                
                results = await pipe.execute()
                self.stats["pipeline_ops"] += len(operations)
                return results
                
        except Exception as e:
            logger.error(f"管道操作失败: {e}")
            return []
    
    async def lua_batch_operations(
        self, 
        keys: List[str], 
        operations: List[str], 
        values: List[str]
    ) -> List[Any]:
        """使用Lua脚本进行批量操作"""
        try:
            result = await self.redis.evalsha(
                self.script_shas["batch_operations"],
                len(keys),
                *keys,
                len(keys),
                *operations,
                *values
            )
            
            self.stats["lua_script_ops"] += 1
            return result
            
        except Exception as e:
            logger.error(f"Lua批量操作失败: {e}")
            return []
    
    async def prevent_cache_avalanche(
        self, 
        key: str, 
        value: Any, 
        base_ttl: int,
        variance_percent: int = 20
    ) -> int:
        """防缓存雪崩的设置方法"""
        try:
            serialized_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            variance = int(base_ttl * variance_percent / 100)
            
            actual_ttl = await self.redis.evalsha(
                self.script_shas["set_with_random_ttl"],
                1,
                key,
                serialized_value,
                base_ttl,
                variance
            )
            
            return actual_ttl
            
        except Exception as e:
            logger.error(f"防雪崩设置失败: {key}, {e}")
            return 0
    
    async def cache_aside_get(
        self, 
        key: str, 
        fetch_func,
        ttl: Optional[int] = None,
        key_type: str = "default"
    ) -> Any:
        """
        Cache-Aside模式获取数据
        如果缓存不存在，自动从数据源获取并缓存
        """
        # 首先检查布隆过滤器
        if not await self.bloom_filter.contains(key, key_type):
            # 布隆过滤器表示数据肯定不存在，直接返回None
            return None
        
        # 尝试从缓存获取
        value = await self.get(key)
        if value is not None:
            return value
        
        # 缓存未命中，从数据源获取
        try:
            if asyncio.iscoroutinefunction(fetch_func):
                fresh_value = await fetch_func()
            else:
                fresh_value = fetch_func()
            
            if fresh_value is not None:
                await self.set(key, fresh_value, ttl, key_type)
            
            return fresh_value
            
        except Exception as e:
            logger.error(f"从数据源获取数据失败: {key}, {e}")
            return None
    
    async def get_lock(self, lock_key: str, **kwargs) -> DistributedLock:
        """获取分布式锁实例"""
        return DistributedLock(self.redis, lock_key, **kwargs)
    
    @asynccontextmanager
    async def lock(self, lock_key: str, **kwargs):
        """分布式锁上下文管理器"""
        async with distributed_lock(self.redis, lock_key, **kwargs) as lock:
            yield lock
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        info = await self.redis.info()
        
        hit_rate = 0
        total_ops = self.stats["hits"] + self.stats["misses"]
        if total_ops > 0:
            hit_rate = self.stats["hits"] / total_ops
        
        return {
            "cache_stats": self.stats.copy(),
            "hit_rate": hit_rate,
            "redis_info": {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
            },
            "connection_pool": {
                "created_connections": self.pool.created_connections,
                "available_connections": len(self.pool._available_connections),
                "in_use_connections": len(self.pool._in_use_connections)
            }
        }
    
    async def clear_stats(self) -> None:
        """清空统计信息"""
        self.stats = {
            "hits": 0,
            "misses": 0, 
            "sets": 0,
            "deletes": 0,
            "pipeline_ops": 0,
            "lua_script_ops": 0
        }
    
    async def preheat_cache(self, data_fetch_funcs: Dict[str, callable]) -> None:
        """缓存预热"""
        logger.info("开始缓存预热...")
        
        for pattern, fetch_func in data_fetch_funcs.items():
            try:
                if asyncio.iscoroutinefunction(fetch_func):
                    data = await fetch_func()
                else:
                    data = fetch_func()
                
                if isinstance(data, dict):
                    # 批量设置
                    ops = []
                    for key, value in data.items():
                        ops.append({
                            "cmd": "set",
                            "key": key,
                            "value": json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                            "ttl": self._get_ttl("config") if pattern.startswith("config") else None
                        })
                    
                    await self.pipeline_operations(ops)
                    logger.info(f"预热数据: {pattern}, 数量: {len(data)}")
                
            except Exception as e:
                logger.error(f"预热数据失败: {pattern}, {e}")
        
        logger.info("缓存预热完成")


# 全局缓存实例
_cache_instance: Optional[RedisCache] = None


async def get_redis_cache() -> RedisCache:
    """获取全局Redis缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache()
        await _cache_instance.connect()
    return _cache_instance


async def close_redis_cache() -> None:
    """关闭全局Redis缓存实例"""
    global _cache_instance
    if _cache_instance is not None:
        await _cache_instance.disconnect()
        _cache_instance = None