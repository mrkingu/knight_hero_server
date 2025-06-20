"""
增强版BaseRepository - 在数据层自动处理并发问题
所有数据修改都通过原子操作保证并发安全
作者: lx
日期: 2025-06-18
"""
import asyncio
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, Callable, Tuple, Generic
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from beanie import Document

from .redis_cache import RedisCache
from .mongo_client import MongoClient
from .operation_logger import OperationLogger
from .concurrent_operations import (
    ConcurrentOperation, OperationType, OperationResult, 
    ConcurrentOperationManager
)
from .distributed_lock import distributed_lock
from .models import get_concurrent_fields

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Document)


class BaseRepository(ABC, Generic[T]):
    """基础仓库类，提供并发安全的数据访问"""
    
    def __init__(
        self,
        redis_client: RedisCache,
        mongo_client: MongoClient,
        collection_name: str,
        document_class: Type[T],
        cache_ttl: int = 300,
        persistence_interval: float = 300.0,  # 5分钟持久化一次
        operation_timeout: float = 10.0  # 单个操作队列处理超时
    ):
        """
        初始化基础仓库
        
        Args:
            redis_client: Redis缓存客户端
            mongo_client: MongoDB客户端
            collection_name: 集合名称
            document_class: 文档类
            cache_ttl: 缓存TTL(秒)
            persistence_interval: 持久化间隔(秒)
            operation_timeout: 操作超时时间(秒)
        """
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.collection_name = collection_name
        self.document_class = document_class
        self.cache_ttl = cache_ttl
        self.persistence_interval = persistence_interval
        self.operation_timeout = operation_timeout
        
        # 并发操作管理器
        self.operation_manager = ConcurrentOperationManager()
        
        # 操作日志记录器
        self.operation_logger: Optional[OperationLogger] = None
        
        # 脏数据标记 - 用于跟踪需要持久化的数据
        self.dirty_entities: set = set()
        self.dirty_lock = asyncio.Lock()
        
        # 幂等性追踪 - 防止重复处理
        self.processed_orders: Dict[str, datetime] = {}  # 支付订单
        self.processed_tasks: Dict[str, datetime] = {}   # 定时任务
        
        # 后台任务
        self._operation_processor_task: Optional[asyncio.Task] = None
        self._persistence_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # 统计信息
        self.stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "persistence_operations": 0,
            "concurrent_conflicts": 0,
            "lock_timeouts": 0
        }
        
        # 并发字段配置
        self.concurrent_fields = get_concurrent_fields(document_class)
    
    async def start(self, operation_logger: OperationLogger) -> None:
        """启动仓库后台任务"""
        self.operation_logger = operation_logger
        
        if self._operation_processor_task is None:
            self._operation_processor_task = asyncio.create_task(
                self._operation_processor_worker()
            )
        
        if self._persistence_task is None:
            self._persistence_task = asyncio.create_task(
                self._persistence_worker()
            )
        
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_worker()
            )
        
        logger.info(f"仓库 {self.collection_name} 已启动")
    
    async def stop(self) -> None:
        """停止仓库后台任务"""
        self._shutdown = True
        
        # 停止所有后台任务
        tasks = [
            self._operation_processor_task,
            self._persistence_task,
            self._cleanup_task
        ]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 处理剩余操作
        await self._process_remaining_operations()
        
        # 持久化所有脏数据
        await self._persist_all_dirty_entities()
        
        logger.info(f"仓库 {self.collection_name} 已停止")
    
    async def get(self, entity_id: str, use_cache: bool = True) -> Optional[T]:
        """获取实体"""
        cache_key = f"{self.collection_name}:{entity_id}"
        
        if use_cache:
            # 首先尝试从缓存获取
            cached_data = await self.redis_client.get(cache_key)
            if cached_data is not None:
                self.stats["cache_hits"] += 1
                try:
                    # 将字典数据转换为文档对象
                    if isinstance(cached_data, dict):
                        return self.document_class(**cached_data)
                    return cached_data
                except Exception as e:
                    logger.error(f"缓存数据反序列化失败: {e}")
        
        # 缓存未命中，从数据库获取
        self.stats["cache_misses"] += 1
        
        try:
            document = await self.document_class.find_one(
                self.document_class.id == entity_id
            )
            
            if document and use_cache:
                # 缓存到Redis
                await self.redis_client.set(
                    cache_key,
                    document.model_dump(),
                    ttl=self.cache_ttl,
                    key_type=self.collection_name
                )
            
            return document
            
        except Exception as e:
            logger.error(f"获取实体失败: {entity_id}, {e}")
            return None
    
    async def create(
        self, 
        entity_data: Dict[str, Any], 
        cache: bool = True
    ) -> Optional[T]:
        """创建新实体"""
        try:
            document = self.document_class(**entity_data)
            await document.save()
            
            if cache:
                cache_key = f"{self.collection_name}:{document.id}"
                await self.redis_client.set(
                    cache_key,
                    document.model_dump(),
                    ttl=self.cache_ttl,
                    key_type=self.collection_name
                )
            
            # 记录创建日志
            if self.operation_logger:
                await self.operation_logger.log_operation(
                    entity_type=self.collection_name,
                    entity_id=str(document.id),
                    operation_type="create",
                    field_name="*",
                    new_value=entity_data,
                    source="repository",
                    reason="entity_created"
                )
            
            return document
            
        except Exception as e:
            logger.error(f"创建实体失败: {e}")
            return None
    
    async def increment(
        self,
        entity_id: str,
        field: str,
        value: Union[int, float],
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """原子增量操作"""
        return await self._execute_atomic_operation(
            entity_id=entity_id,
            field=field,
            operation=OperationType.INCREMENT,
            value=value,
            source=source,
            reason=reason,
            metadata=metadata
        )
    
    async def decrement(
        self,
        entity_id: str,
        field: str,
        value: Union[int, float],
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """原子减量操作"""
        return await self._execute_atomic_operation(
            entity_id=entity_id,
            field=field,
            operation=OperationType.DECREMENT,
            value=value,
            source=source,
            reason=reason,
            metadata=metadata
        )
    
    async def decrement_with_check(
        self,
        entity_id: str,
        field: str,
        value: Union[int, float],
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """带检查的原子减量操作(确保不会小于最小值)"""
        field_config = self.concurrent_fields.get(field, {})
        min_value = field_config.get("min", 0)
        
        # 使用分布式锁确保原子性
        lock_key = f"entity_lock:{self.collection_name}:{entity_id}"
        
        async with distributed_lock(self.redis_client.redis, lock_key, timeout=30.0):
            try:
                # 获取当前值
                current_entity = await self.get(entity_id)
                if not current_entity:
                    return {
                        "success": False,
                        "reason": "entity_not_found",
                        "entity_id": entity_id
                    }
                
                current_value = getattr(current_entity, field, 0)
                new_value = current_value - value
                
                if new_value < min_value:
                    return {
                        "success": False,
                        "reason": "insufficient_balance",
                        "current_value": current_value,
                        "required": value,
                        "shortage": min_value - new_value
                    }
                
                # 执行减量操作
                return await self.decrement(
                    entity_id, field, value, source, reason, metadata
                )
                
            except Exception as e:
                logger.error(f"带检查的减量操作失败: {e}")
                return {
                    "success": False,
                    "reason": "operation_error",
                    "error": str(e)
                }
    
    async def set_field(
        self,
        entity_id: str,
        field: str,
        value: Any,
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """原子设置操作"""
        return await self._execute_atomic_operation(
            entity_id=entity_id,
            field=field,
            operation=OperationType.SET,
            value=value,
            source=source,
            reason=reason,
            metadata=metadata
        )
    
    async def batch_modify(
        self,
        entity_id: str,
        operations: List[Dict[str, Any]],
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """批量原子操作"""
        lock_key = f"entity_lock:{self.collection_name}:{entity_id}"
        
        async with distributed_lock(self.redis_client.redis, lock_key, timeout=30.0):
            try:
                results = []
                entity = await self.get(entity_id)
                
                if not entity:
                    return {
                        "success": False,
                        "reason": "entity_not_found",
                        "entity_id": entity_id
                    }
                
                # 验证所有操作
                for op in operations:
                    field = op["field"]
                    operation_type = op["operation"]
                    value = op["value"]
                    
                    if not self._validate_operation(field, operation_type, value, entity):
                        return {
                            "success": False,
                            "reason": "validation_failed",
                            "field": field,
                            "operation": operation_type.value if hasattr(operation_type, 'value') else str(operation_type)
                        }
                
                # 执行所有操作
                for op in operations:
                    field = op["field"]
                    operation_type = op["operation"]
                    value = op["value"]
                    
                    old_value = getattr(entity, field, None)
                    new_value = self._calculate_new_value(old_value, operation_type, value)
                    
                    setattr(entity, field, new_value)
                    
                    results.append({
                        "field": field,
                        "old_value": old_value,
                        "new_value": new_value,
                        "operation": operation_type.value if hasattr(operation_type, 'value') else str(operation_type)
                    })
                    
                    # 记录操作日志
                    if self.operation_logger:
                        await self.operation_logger.log_operation(
                            entity_type=self.collection_name,
                            entity_id=entity_id,
                            operation_type=operation_type.value if hasattr(operation_type, 'value') else str(operation_type),
                            field_name=field,
                            old_value=old_value,
                            new_value=new_value,
                            source=source,
                            reason=reason,
                            metadata=metadata
                        )
                
                # 更新缓存
                await self._update_cache(entity_id, entity)
                
                # 标记为脏数据
                await self._mark_dirty(entity_id)
                
                self.stats["successful_operations"] += len(operations)
                
                return {
                    "success": True,
                    "entity_id": entity_id,
                    "operations_count": len(operations),
                    "results": results
                }
                
            except Exception as e:
                logger.error(f"批量操作失败: {e}")
                self.stats["failed_operations"] += len(operations)
                return {
                    "success": False,
                    "reason": "operation_error",
                    "error": str(e)
                }
    
    async def _execute_atomic_operation(
        self,
        entity_id: str,
        field: str,
        operation: OperationType,
        value: Any,
        source: str = "",
        reason: str = "",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """执行原子操作"""
        # 添加操作到队列
        concurrent_op = ConcurrentOperation(
            field=field,
            operation=operation,
            value=value,
            metadata={
                "source": source,
                "reason": reason,
                "custom_metadata": metadata or {}
            }
        )
        
        self.operation_manager.add_operation(entity_id, concurrent_op)
        self.stats["total_operations"] += 1
        
        # 如果队列处理器还没处理到这个实体，我们可以立即处理
        # 这样减少延迟
        if entity_id not in self.operation_manager.processing_entities:
            await self._process_entity_operations(entity_id)
        
        return {
            "success": True,
            "entity_id": entity_id,
            "field": field,
            "operation": operation.value,
            "queued": True
        }
    
    async def _process_entity_operations(self, entity_id: str) -> None:
        """处理单个实体的操作队列"""
        if not self.operation_manager.start_processing(entity_id):
            return  # 已经在处理中
        
        try:
            lock_key = f"entity_lock:{self.collection_name}:{entity_id}"
            timeout = self.operation_timeout
            
            async with distributed_lock(
                self.redis_client.redis, 
                lock_key, 
                timeout=timeout
            ):
                queue = self.operation_manager.entity_queues.get(entity_id)
                if not queue:
                    return
                
                # 获取批量操作
                operations = queue.get_next_batch(max_size=10)
                if not operations:
                    return
                
                # 获取实体
                entity = await self.get(entity_id)
                if not entity:
                    logger.error(f"实体不存在: {entity_id}")
                    self.stats["failed_operations"] += len(operations)
                    return
                
                # 执行所有操作
                success_count = 0
                for op in operations:
                    if await self._apply_operation(entity, op):
                        success_count += 1
                
                # 更新缓存
                await self._update_cache(entity_id, entity)
                
                # 标记为脏数据
                await self._mark_dirty(entity_id)
                
                self.stats["successful_operations"] += success_count
                self.stats["failed_operations"] += len(operations) - success_count
                
        except Exception as e:
            logger.error(f"处理实体操作失败: {entity_id}, {e}")
            self.stats["failed_operations"] += 1
        finally:
            self.operation_manager.finish_processing(entity_id)
    
    async def _apply_operation(self, entity: T, operation: ConcurrentOperation) -> bool:
        """应用单个操作到实体"""
        try:
            field = operation.field
            op_type = operation.operation
            value = operation.value
            metadata = operation.metadata
            
            # 验证操作
            if not self._validate_operation(field, op_type, value, entity):
                return False
            
            old_value = getattr(entity, field, None)
            new_value = self._calculate_new_value(old_value, op_type, value)
            
            # 检查边界
            if not operation.check_bounds(old_value, new_value):
                logger.warning(f"操作超出边界: {field}, {old_value} -> {new_value}")
                return False
            
            # 应用更改
            setattr(entity, field, new_value)
            
            # 记录操作日志
            if self.operation_logger:
                await self.operation_logger.log_operation(
                    entity_type=self.collection_name,
                    entity_id=str(entity.id),
                    operation_type=op_type.value,
                    field_name=field,
                    old_value=old_value,
                    new_value=new_value,
                    source=metadata.get("source", ""),
                    reason=metadata.get("reason", ""),
                    metadata=metadata.get("custom_metadata")
                )
            
            return True
            
        except Exception as e:
            logger.error(f"应用操作失败: {e}")
            return False
    
    def _validate_operation(
        self, 
        field: str, 
        operation: OperationType, 
        value: Any, 
        entity: T
    ) -> bool:
        """验证操作是否合法"""
        field_config = self.concurrent_fields.get(field)
        if not field_config:
            logger.warning(f"字段 {field} 不支持并发操作")
            return False
        
        allowed_ops = field_config.get("operations", [])
        if operation.value not in allowed_ops:
            logger.warning(f"字段 {field} 不支持操作 {operation.value}")
            return False
        
        # 类型检查
        field_type = field_config.get("type", "any")
        if field_type == "number" and not isinstance(value, (int, float)):
            logger.warning(f"字段 {field} 期望数字类型，得到 {type(value)}")
            return False
        
        return True
    
    def _calculate_new_value(
        self, 
        current_value: Any, 
        operation: OperationType, 
        value: Any
    ) -> Any:
        """计算新值"""
        if operation == OperationType.SET:
            return value
        elif operation == OperationType.INCREMENT:
            return (current_value or 0) + value
        elif operation == OperationType.DECREMENT:
            return (current_value or 0) - value
        elif operation == OperationType.MULTIPLY:
            return (current_value or 0) * value
        elif operation == OperationType.APPEND:
            if isinstance(current_value, list):
                return current_value + [value]
            return [value]
        elif operation == OperationType.REMOVE:
            if isinstance(current_value, list) and value in current_value:
                new_list = current_value.copy()
                new_list.remove(value)
                return new_list
            return current_value
        else:
            return current_value
    
    async def _update_cache(self, entity_id: str, entity: T) -> None:
        """更新缓存"""
        cache_key = f"{self.collection_name}:{entity_id}"
        await self.redis_client.set(
            cache_key,
            entity.model_dump(),
            ttl=self.cache_ttl,
            key_type=self.collection_name
        )
    
    async def _mark_dirty(self, entity_id: str) -> None:
        """标记实体为脏数据"""
        async with self.dirty_lock:
            self.dirty_entities.add(entity_id)
    
    async def _operation_processor_worker(self) -> None:
        """操作处理工作任务"""
        while not self._shutdown:
            try:
                entity_id = self.operation_manager.get_next_entity_to_process()
                if entity_id:
                    await self._process_entity_operations(entity_id)
                else:
                    await asyncio.sleep(0.01)  # 10ms 间隔
            except Exception as e:
                logger.error(f"操作处理工作任务错误: {e}")
                await asyncio.sleep(0.1)
    
    async def _persistence_worker(self) -> None:
        """持久化工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.persistence_interval)
                await self._persist_dirty_entities()
            except Exception as e:
                logger.error(f"持久化工作任务错误: {e}")
    
    async def _cleanup_worker(self) -> None:
        """清理工作任务"""
        cleanup_interval = 3600  # 每小时清理一次
        
        while not self._shutdown:
            try:
                await asyncio.sleep(cleanup_interval)
                await self._cleanup_processed_items()
            except Exception as e:
                logger.error(f"清理工作任务错误: {e}")
    
    async def _persist_dirty_entities(self) -> None:
        """持久化脏数据实体"""
        async with self.dirty_lock:
            entities_to_persist = list(self.dirty_entities)
            self.dirty_entities.clear()
        
        if not entities_to_persist:
            return
        
        try:
            persist_count = 0
            for entity_id in entities_to_persist:
                entity = await self.get(entity_id, use_cache=True)
                if entity:
                    await entity.save()
                    persist_count += 1
            
            self.stats["persistence_operations"] += persist_count
            logger.debug(f"持久化完成: {persist_count} 个实体")
            
        except Exception as e:
            logger.error(f"持久化失败: {e}")
            # 失败时重新标记为脏数据
            async with self.dirty_lock:
                self.dirty_entities.update(entities_to_persist)
    
    async def _persist_all_dirty_entities(self) -> None:
        """持久化所有脏数据"""
        await self._persist_dirty_entities()
    
    async def _process_remaining_operations(self) -> None:
        """处理剩余的操作"""
        while True:
            entity_id = self.operation_manager.get_next_entity_to_process()
            if not entity_id:
                break
            await self._process_entity_operations(entity_id)
    
    async def _cleanup_processed_items(self) -> None:
        """清理已处理的项目"""
        cutoff_time = datetime.now() - timedelta(hours=24)
        
        # 清理过期的订单记录
        self.processed_orders = {
            k: v for k, v in self.processed_orders.items()
            if v > cutoff_time
        }
        
        # 清理过期的任务记录
        self.processed_tasks = {
            k: v for k, v in self.processed_tasks.items()
            if v > cutoff_time
        }
    
    async def _check_order_processed(self, order_id: str) -> bool:
        """检查订单是否已处理"""
        return order_id in self.processed_orders
    
    async def _mark_order_processed(self, order_id: str) -> None:
        """标记订单已处理"""
        self.processed_orders[order_id] = datetime.now()
    
    async def _check_task_rewarded(self, player_id: str, task_id: str) -> bool:
        """检查任务是否已发放奖励"""
        key = f"{player_id}:{task_id}"
        return key in self.processed_tasks
    
    async def _mark_task_rewarded(self, player_id: str, task_id: str) -> None:
        """标记任务已发放奖励"""
        key = f"{player_id}:{task_id}"
        self.processed_tasks[key] = datetime.now()
    
    async def force_persistence(self, entity_id: Optional[str] = None) -> None:
        """强制持久化"""
        if entity_id:
            async with self.dirty_lock:
                if entity_id in self.dirty_entities:
                    self.dirty_entities.remove(entity_id)
                    entity = await self.get(entity_id, use_cache=True)
                    if entity:
                        await entity.save()
        else:
            await self._persist_all_dirty_entities()
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取仓库统计信息"""
        queue_stats = self.operation_manager.get_queue_stats()
        
        async with self.dirty_lock:
            dirty_count = len(self.dirty_entities)
        
        return {
            "collection": self.collection_name,
            "operation_stats": self.stats.copy(),
            "queue_stats": queue_stats,
            "dirty_entities": dirty_count,
            "processed_orders": len(self.processed_orders),
            "processed_tasks": len(self.processed_tasks),
            "concurrent_fields": len(self.concurrent_fields)
        }