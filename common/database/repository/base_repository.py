"""
仓库基类
提供统一的数据访问接口，自动处理缓存和并发
作者: lx
日期: 2025-06-20
"""
import asyncio
from typing import TypeVar, Generic, Optional, Dict, Any, List
from abc import ABC, abstractmethod

T = TypeVar('T')

class BaseRepository(Generic[T], ABC):
    """数据仓库基类"""
    
    def __init__(self, redis_client, mongo_client, collection_name: str):
        """
        初始化仓库
        
        Args:
            redis_client: Redis客户端
            mongo_client: MongoDB客户端
            collection_name: 集合名称
        """
        self.redis = redis_client
        self.mongo = mongo_client
        self.collection_name = collection_name
        
        # 操作队列：每个实体一个队列
        self._queues: Dict[str, asyncio.Queue] = {}
        self._workers: Dict[str, asyncio.Task] = {}
        
    @abstractmethod
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """获取支持并发操作的字段配置"""
        pass
        
    async def get(self, entity_id: str) -> Optional[T]:
        """
        获取实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            实体对象或None
        """
        # 1. 尝试从缓存获取
        cache_key = f"{self.collection_name}:{entity_id}"
        cached_data = await self.redis.client.hgetall(cache_key)
        
        if cached_data:
            return self._deserialize(cached_data)
            
        # 2. 从数据库加载
        db_data = await self.mongo[self.collection_name].find_one({"_id": entity_id})
        
        if db_data:
            # 3. 写入缓存
            await self._cache_entity(entity_id, db_data)
            return self._deserialize(db_data)
            
        return None
        
    async def save(self, entity_id: str, entity: T) -> bool:
        """
        保存实体（全量更新）
        
        Args:
            entity_id: 实体ID
            entity: 实体对象
            
        Returns:
            是否成功
        """
        data = self._serialize(entity)
        
        # 更新缓存
        cache_key = f"{self.collection_name}:{entity_id}"
        await self.redis.client.hset(cache_key, mapping=data)
        await self.redis.client.expire(cache_key, 3600)  # 1小时过期
        
        # 标记需要持久化
        await self._mark_dirty(entity_id)
        
        return True
        
    async def modify_field(
        self,
        entity_id: str,
        field: str,
        operation: str,
        value: Any,
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        修改单个字段（并发安全）
        
        Args:
            entity_id: 实体ID
            field: 字段名
            operation: 操作类型
            value: 操作值
            source: 操作来源
            
        Returns:
            操作结果
        """
        # 创建操作请求
        request = {
            "field": field,
            "operation": operation,
            "value": value,
            "source": source,
            "future": asyncio.Future()
        }
        
        # 提交到队列
        await self._submit_operation(entity_id, request)
        
        # 等待结果
        return await request["future"]
        
    async def _submit_operation(self, entity_id: str, request: Dict[str, Any]):
        """提交操作到队列"""
        # 确保有队列
        if entity_id not in self._queues:
            self._queues[entity_id] = asyncio.Queue(maxsize=1000)
            
        # 确保有工作协程
        if entity_id not in self._workers or self._workers[entity_id].done():
            worker = asyncio.create_task(self._process_queue(entity_id))
            self._workers[entity_id] = worker
            
        # 加入队列
        await self._queues[entity_id].put(request)
        
    async def _process_queue(self, entity_id: str):
        """处理实体的操作队列"""
        queue = self._queues[entity_id]
        
        while True:
            try:
                # 批量获取操作
                batch = []
                timeout = 0.01  # 10ms
                
                while len(batch) < 10:
                    try:
                        request = await asyncio.wait_for(queue.get(), timeout=timeout)
                        batch.append(request)
                    except asyncio.TimeoutError:
                        break
                        
                if batch:
                    # 批量执行
                    await self._execute_batch(entity_id, batch)
                elif queue.empty():
                    # 空闲退出
                    await asyncio.sleep(60)
                    if queue.empty():
                        break
                        
            except Exception as e:
                print(f"Queue process error: {e}")
                
        # 清理
        del self._queues[entity_id]
        del self._workers[entity_id]
        
    async def _execute_batch(self, entity_id: str, batch: List[Dict[str, Any]]):
        """批量执行操作"""
        cache_key = f"{self.collection_name}:{entity_id}"
        
        # 使用Lua脚本批量执行
        from ..utils.lua_scripts import LuaScripts
        
        for request in batch:
            try:
                field = request["field"]
                operation = request["operation"]
                value = request["value"]
                
                if operation == "incr":
                    # 执行增加操作
                    result = await self.redis.client.eval(
                        LuaScripts.INCR_WITH_LIMIT,
                        1,
                        cache_key,
                        field,
                        value,
                        0,  # min
                        999999999  # max
                    )
                    
                    request["future"].set_result({
                        "success": True,
                        "old_value": result[0],
                        "new_value": result[1]
                    })
                else:
                    # 其他操作类型的处理
                    request["future"].set_result({"success": False, "reason": "unsupported_operation"})
                    
            except Exception as e:
                request["future"].set_exception(e)
                
        # 标记为脏数据需要持久化
        await self._mark_dirty(entity_id)
        
    async def _cache_entity(self, entity_id: str, data: Dict[str, Any]):
        """缓存实体数据"""
        cache_key = f"{self.collection_name}:{entity_id}"
        # 转换数据类型为字符串
        string_data = {k: str(v) for k, v in data.items()}
        await self.redis.client.hset(cache_key, mapping=string_data)
        await self.redis.client.expire(cache_key, 3600)
        
    async def _mark_dirty(self, entity_id: str):
        """标记实体为脏数据"""
        dirty_key = f"dirty:{self.collection_name}:{entity_id}"
        await self.redis.client.set(dirty_key, "1", ex=3600)
        
    def _serialize(self, entity: T) -> Dict[str, Any]:
        """序列化实体"""
        if hasattr(entity, 'dict'):
            return entity.dict()
        elif isinstance(entity, dict):
            return entity
        else:
            return entity.__dict__
            
    def _deserialize(self, data: Dict[str, Any]) -> T:
        """反序列化实体"""
        # 简单返回字典，子类可以重写
        return data