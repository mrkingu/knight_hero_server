"""
会话管理器模块
Session Manager Module

作者: lx
日期: 2025-06-18
描述: 负责会话的Redis存储、本地缓存、续期管理、分布式同步等
"""
import asyncio
import json
import time
from typing import Dict, List, Optional, Set, Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

from common.database import get_redis_cache, RedisClient

if TYPE_CHECKING:
    from .session import Session
    from .connection import Connection


@dataclass
class SessionManagerConfig:
    """会话管理器配置"""
    # 缓存配置
    LOCAL_CACHE_SIZE: int = 5000      # 本地缓存大小
    HOT_SESSION_THRESHOLD: int = 10   # 热点会话阈值（访问次数）
    
    # 续期配置
    DEFAULT_SESSION_TTL: int = 30 * 60  # 默认会话TTL（30分钟）
    RENEWAL_THRESHOLD: int = 5 * 60     # 续期阈值（5分钟）
    AUTO_RENEWAL: bool = True           # 自动续期
    
    # 同步配置
    SYNC_INTERVAL: int = 30            # 同步间隔（秒）
    BATCH_SYNC_SIZE: int = 100         # 批量同步大小
    
    # 清理配置
    CLEANUP_INTERVAL: int = 60         # 清理间隔（秒）
    MAX_INACTIVE_TIME: int = 60 * 60   # 最大非活跃时间（1小时）
    
    # Redis键前缀
    REDIS_SESSION_PREFIX: str = "gateway:session:"
    REDIS_USER_SESSION_PREFIX: str = "gateway:user_sessions:"
    REDIS_STATS_KEY: str = "gateway:session_stats"


class SessionCache:
    """本地会话缓存"""
    
    def __init__(self, max_size: int = 5000):
        """
        初始化会话缓存
        
        Args:
            max_size: 最大缓存大小
        """
        self.max_size = max_size
        self.cache: Dict[int, 'Session'] = {}
        self.access_count: Dict[int, int] = {}
        self.access_time: Dict[int, float] = {}
        
        # 锁
        self._lock = asyncio.Lock()
    
    async def get(self, session_id: int) -> Optional['Session']:
        """
        获取会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话对象，不存在返回None
        """
        async with self._lock:
            session = self.cache.get(session_id)
            if session:
                self.access_count[session_id] = self.access_count.get(session_id, 0) + 1
                self.access_time[session_id] = time.time()
            return session
    
    async def put(self, session: 'Session') -> bool:
        """
        存储会话
        
        Args:
            session: 会话对象
            
        Returns:
            是否成功存储
        """
        async with self._lock:
            # 检查缓存空间
            if len(self.cache) >= self.max_size and session.id not in self.cache:
                # 移除最少使用的会话
                await self._evict_lru()
            
            self.cache[session.id] = session
            self.access_count[session.id] = self.access_count.get(session.id, 0) + 1
            self.access_time[session.id] = time.time()
            return True
    
    async def remove(self, session_id: int) -> Optional['Session']:
        """
        移除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            被移除的会话对象
        """
        async with self._lock:
            session = self.cache.pop(session_id, None)
            self.access_count.pop(session_id, None)
            self.access_time.pop(session_id, None)
            return session
    
    async def clear(self) -> None:
        """清空缓存"""
        async with self._lock:
            self.cache.clear()
            self.access_count.clear()
            self.access_time.clear()
    
    async def _evict_lru(self) -> None:
        """移除最少使用的会话"""
        if not self.access_time:
            return
        
        # 找到最久未访问的会话
        oldest_session_id = min(self.access_time.keys(), key=lambda k: self.access_time[k])
        
        # 移除会话
        self.cache.pop(oldest_session_id, None)
        self.access_count.pop(oldest_session_id, None)
        self.access_time.pop(oldest_session_id, None)
    
    def get_hot_sessions(self, threshold: int) -> Set[int]:
        """
        获取热点会话ID集合
        
        Args:
            threshold: 访问次数阈值
            
        Returns:
            热点会话ID集合
        """
        return {
            session_id for session_id, count in self.access_count.items()
            if count >= threshold
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hit_rate': len([c for c in self.access_count.values() if c > 1]) / max(1, len(self.access_count)),
            'total_access': sum(self.access_count.values()),
            'hot_sessions': len(self.get_hot_sessions(10))
        }


class SessionManager:
    """
    会话管理器
    
    负责会话的完整生命周期管理，包括创建、存储、缓存、续期、同步、清理等
    """
    
    def __init__(self, config: Optional[SessionManagerConfig] = None):
        """
        初始化会话管理器
        
        Args:
            config: 会话管理器配置
        """
        self.config = config or SessionManagerConfig()
        
        # Redis客户端
        self.redis_client: Optional[RedisClient] = None
        
        # 本地缓存
        self.local_cache = SessionCache(self.config.LOCAL_CACHE_SIZE)
        
        # 会话索引
        self.user_sessions: Dict[str, Set[int]] = {}  # 用户ID -> 会话ID集合
        self.active_sessions: Set[int] = set()        # 活跃会话ID集合
        
        # 统计信息
        self.total_created = 0           # 总创建会话数
        self.total_destroyed = 0         # 总销毁会话数
        self.total_renewals = 0          # 总续期次数
        self.cache_hits = 0             # 缓存命中次数
        self.cache_misses = 0           # 缓存未命中次数
        self.redis_operations = 0        # Redis操作次数
        
        # 任务管理
        self._sync_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 锁
        self._session_lock = asyncio.Lock()
        self._index_lock = asyncio.Lock()
        
        # 状态标志
        self._shutting_down = False
        self._initialized = False
    
    async def initialize(self) -> bool:
        """
        初始化会话管理器
        
        Returns:
            是否成功初始化
        """
        try:
            # 获取Redis客户端
            self.redis_client = await get_redis_cache()
            
            # 启动后台任务
            await self._start_background_tasks()
            
            self._initialized = True
            return True
            
        except Exception as e:
            return False
    
    async def shutdown(self) -> None:
        """关闭会话管理器"""
        self._shutting_down = True
        
        # 停止后台任务
        await self._stop_background_tasks()
        
        # 同步所有会话到Redis
        await self._sync_all_sessions()
        
        # 清理资源
        await self.local_cache.clear()
        self.user_sessions.clear()
        self.active_sessions.clear()
    
    async def create_session(self, connection: 'Connection') -> Optional['Session']:
        """
        创建新会话
        
        Args:
            connection: WebSocket连接对象
            
        Returns:
            创建的会话对象，失败返回None
        """
        try:
            from .session import Session
            
            async with self._session_lock:
                # 创建会话对象
                session = Session(connection)
                connection.session = session
                
                # 添加到本地缓存
                await self.local_cache.put(session)
                
                # 添加到活跃会话集合
                self.active_sessions.add(session.id)
                
                # 保存到Redis
                await self._save_session_to_redis(session)
                
                # 更新统计
                self.total_created += 1
                
                return session
                
        except Exception as e:
            return None
    
    async def get_session(self, session_id: int) -> Optional['Session']:
        """
        获取会话对象
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话对象，不存在返回None
        """
        # 尝试从本地缓存获取
        session = await self.local_cache.get(session_id)
        if session:
            self.cache_hits += 1
            return session
        
        # 从Redis加载
        session = await self._load_session_from_redis(session_id)
        if session:
            # 加入本地缓存
            await self.local_cache.put(session)
            self.cache_misses += 1
            return session
        
        self.cache_misses += 1
        return None
    
    async def remove_session(self, session_id: int) -> bool:
        """
        移除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功移除
        """
        try:
            async with self._session_lock:
                # 从本地缓存移除
                session = await self.local_cache.remove(session_id)
                
                # 从活跃会话集合移除
                self.active_sessions.discard(session_id)
                
                # 从用户会话索引移除
                if session and session.attributes.user_id:
                    async with self._index_lock:
                        user_sessions = self.user_sessions.get(session.attributes.user_id, set())
                        user_sessions.discard(session_id)
                        if not user_sessions:
                            self.user_sessions.pop(session.attributes.user_id, None)
                
                # 从Redis删除
                await self._delete_session_from_redis(session_id)
                
                # 更新统计
                self.total_destroyed += 1
                
                return True
                
        except Exception as e:
            return False
    
    async def authenticate_session(self, session_id: int, user_id: str, **kwargs) -> bool:
        """
        认证会话
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            **kwargs: 其他认证信息
            
        Returns:
            是否成功认证
        """
        session = await self.get_session(session_id)
        if not session:
            return False
        
        # 执行认证
        success = await session.authenticate(user_id, **kwargs)
        if success:
            # 更新用户会话索引
            async with self._index_lock:
                if user_id not in self.user_sessions:
                    self.user_sessions[user_id] = set()
                self.user_sessions[user_id].add(session_id)
            
            # 保存到Redis
            await self._save_session_to_redis(session)
        
        return success
    
    async def renew_session(self, session_id: int, duration: Optional[int] = None) -> bool:
        """
        续期会话
        
        Args:
            session_id: 会话ID
            duration: 续期时长（秒），None使用默认值
            
        Returns:
            是否成功续期
        """
        session = await self.get_session(session_id)
        if not session:
            return False
        
        duration = duration or self.config.DEFAULT_SESSION_TTL
        success = await session.renew(duration)
        
        if success:
            # 更新Redis
            await self._save_session_to_redis(session)
            self.total_renewals += 1
        
        return success
    
    async def get_user_sessions(self, user_id: str) -> List[int]:
        """
        获取用户的所有会话ID
        
        Args:
            user_id: 用户ID
            
        Returns:
            会话ID列表
        """
        async with self._index_lock:
            return list(self.user_sessions.get(user_id, set()))
    
    async def logout_user(self, user_id: str) -> int:
        """
        登出用户的所有会话
        
        Args:
            user_id: 用户ID
            
        Returns:
            登出的会话数
        """
        session_ids = await self.get_user_sessions(user_id)
        logout_count = 0
        
        for session_id in session_ids:
            session = await self.get_session(session_id)
            if session:
                await session.logout()
                await self._save_session_to_redis(session)
                logout_count += 1
        
        # 清理用户会话索引
        async with self._index_lock:
            self.user_sessions.pop(user_id, None)
        
        return logout_count
    
    async def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话
        
        Returns:
            清理的会话数
        """
        cleaned_count = 0
        expired_sessions = []
        
        # 检查活跃会话
        for session_id in list(self.active_sessions):
            session = await self.get_session(session_id)
            if session and session.is_expired:
                expired_sessions.append(session_id)
        
        # 清理过期会话
        for session_id in expired_sessions:
            await self.remove_session(session_id)
            cleaned_count += 1
        
        return cleaned_count
    
    async def _save_session_to_redis(self, session: 'Session') -> bool:
        """
        保存会话到Redis
        
        Args:
            session: 会话对象
            
        Returns:
            是否成功保存
        """
        try:
            if not self.redis_client:
                return False
            
            # 序列化会话数据
            session_data = session.to_dict()
            session_json = json.dumps(session_data, ensure_ascii=False)
            
            # 保存到Redis
            redis_key = f"{self.config.REDIS_SESSION_PREFIX}{session.id}"
            ttl = self.config.DEFAULT_SESSION_TTL
            
            if session.expires_at:
                ttl = int(session.expires_at - time.time())
                ttl = max(ttl, 60)  # 最少1分钟
            
            await self.redis_client.client.setex(redis_key, ttl, session_json)
            
            # 更新用户会话索引
            if session.attributes.user_id:
                user_key = f"{self.config.REDIS_USER_SESSION_PREFIX}{session.attributes.user_id}"
                await self.redis_client.client.sadd(user_key, str(session.id))
                await self.redis_client.client.expire(user_key, ttl)
            
            self.redis_operations += 1
            return True
            
        except Exception as e:
            return False
    
    async def _load_session_from_redis(self, session_id: int) -> Optional['Session']:
        """
        从Redis加载会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话对象，不存在返回None
        """
        try:
            if not self.redis_client:
                return None
            
            # 从Redis获取会话数据
            redis_key = f"{self.config.REDIS_SESSION_PREFIX}{session_id}"
            session_json = await self.redis_client.client.get(redis_key)
            
            if not session_json:
                return None
            
            # 反序列化会话数据
            session_data = json.loads(session_json)
            
            # 注意：这里无法完全恢复Session对象，因为缺少Connection对象
            # 实际应用中需要特殊处理
            # 这里返回None，表示需要重新创建会话
            
            self.redis_operations += 1
            return None
            
        except Exception as e:
            return None
    
    async def _delete_session_from_redis(self, session_id: int) -> bool:
        """
        从Redis删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功删除
        """
        try:
            if not self.redis_client:
                return False
            
            # 删除会话数据
            redis_key = f"{self.config.REDIS_SESSION_PREFIX}{session_id}"
            await self.redis_client.client.delete(redis_key)
            
            self.redis_operations += 1
            return True
            
        except Exception as e:
            return False
    
    async def _sync_session_stats(self) -> None:
        """同步会话统计信息到Redis"""
        try:
            if not self.redis_client:
                return
            
            stats = self.get_stats()
            stats_json = json.dumps(stats, ensure_ascii=False)
            
            await self.redis_client.client.setex(
                self.config.REDIS_STATS_KEY,
                300,  # 5分钟TTL
                stats_json
            )
            
        except Exception as e:
            pass
    
    async def _sync_all_sessions(self) -> None:
        """同步所有本地会话到Redis"""
        try:
            # 获取所有本地缓存的会话
            sessions_to_sync = list(self.local_cache.cache.values())
            
            # 批量同步
            for i in range(0, len(sessions_to_sync), self.config.BATCH_SYNC_SIZE):
                batch = sessions_to_sync[i:i + self.config.BATCH_SYNC_SIZE]
                
                # 并发保存
                tasks = [self._save_session_to_redis(session) for session in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # 避免阻塞
                await asyncio.sleep(0.001)
                
        except Exception as e:
            pass
    
    async def _sync_loop(self) -> None:
        """同步循环"""
        try:
            while not self._shutting_down:
                await asyncio.sleep(self.config.SYNC_INTERVAL)
                
                if not self._shutting_down:
                    # 同步会话统计
                    await self._sync_session_stats()
                    
                    # 自动续期热点会话
                    if self.config.AUTO_RENEWAL:
                        await self._auto_renew_hot_sessions()
                        
        except Exception as e:
            pass
    
    async def _cleanup_loop(self) -> None:
        """清理循环"""
        try:
            while not self._shutting_down:
                await asyncio.sleep(self.config.CLEANUP_INTERVAL)
                
                if not self._shutting_down:
                    # 清理过期会话
                    cleaned = await self.cleanup_expired_sessions()
                    if cleaned > 0:
                        print(f"清理了 {cleaned} 个过期会话")
                        
        except Exception as e:
            pass
    
    async def _auto_renew_hot_sessions(self) -> None:
        """自动续期热点会话"""
        try:
            # 获取热点会话
            hot_session_ids = self.local_cache.get_hot_sessions(self.config.HOT_SESSION_THRESHOLD)
            
            for session_id in hot_session_ids:
                session = await self.local_cache.get(session_id)
                if session and session.is_authenticated:
                    # 检查是否需要续期
                    if session.expires_at:
                        time_to_expire = session.expires_at - time.time()
                        if time_to_expire < self.config.RENEWAL_THRESHOLD:
                            await self.renew_session(session_id)
                            
        except Exception as e:
            pass
    
    async def _start_background_tasks(self) -> None:
        """启动后台任务"""
        self._sync_task = asyncio.create_task(self._sync_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _stop_background_tasks(self) -> None:
        """停止后台任务"""
        tasks = [
            task for task in [self._sync_task, self._cleanup_task]
            if task and not task.done()
        ]
        
        if tasks:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取会话管理器统计信息
        
        Returns:
            统计信息字典
        """
        cache_stats = self.local_cache.get_stats()
        
        return {
            'active_sessions': len(self.active_sessions),
            'cached_sessions': cache_stats['size'],
            'user_sessions': len(self.user_sessions),
            'total_created': self.total_created,
            'total_destroyed': self.total_destroyed,
            'total_renewals': self.total_renewals,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': self.cache_hits / max(1, self.cache_hits + self.cache_misses),
            'redis_operations': self.redis_operations,
            'local_cache': cache_stats,
            'config': {
                'local_cache_size': self.config.LOCAL_CACHE_SIZE,
                'default_ttl': self.config.DEFAULT_SESSION_TTL,
                'hot_session_threshold': self.config.HOT_SESSION_THRESHOLD,
                'auto_renewal': self.config.AUTO_RENEWAL
            }
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return (f"SessionManager(active={len(self.active_sessions)}, "
                f"cached={len(self.local_cache.cache)}, "
                f"users={len(self.user_sessions)})")
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


# 全局会话管理器实例
_global_session_manager: Optional[SessionManager] = None


async def get_session_manager(config: Optional[SessionManagerConfig] = None) -> SessionManager:
    """
    获取全局会话管理器实例
    
    Args:
        config: 会话管理器配置
        
    Returns:
        会话管理器实例
    """
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager(config)
        await _global_session_manager.initialize()
    return _global_session_manager


async def close_session_manager() -> None:
    """关闭全局会话管理器"""
    global _global_session_manager
    if _global_session_manager:
        await _global_session_manager.shutdown()
        _global_session_manager = None