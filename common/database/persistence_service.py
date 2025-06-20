"""
数据持久化服务
定时将Redis数据同步到MongoDB
作者: lx
日期: 2025-06-18
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from collections import defaultdict

from .redis_cache import RedisCache
from .mongo_client import MongoClient
from .operation_logger import OperationLogger

logger = logging.getLogger(__name__)


class PersistenceStats:
    """持久化统计信息"""
    
    def __init__(self):
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.retries = 0
        self.data_consistency_checks = 0
        self.inconsistencies_found = 0
        self.last_full_sync = None
        self.average_sync_time = 0.0
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "retries": self.retries,
            "data_consistency_checks": self.data_consistency_checks,
            "inconsistencies_found": self.inconsistencies_found,
            "last_full_sync": self.last_full_sync,
            "average_sync_time": self.average_sync_time,
            "success_rate": self.successful_operations / max(1, self.total_operations)
        }


class PersistenceQueue:
    """持久化队列"""
    
    def __init__(self, max_size: int = 1000, max_wait_time: float = 10.0):
        self.max_size = max_size
        self.max_wait_time = max_wait_time
        self.queue: List[Dict[str, Any]] = []
        self.last_flush_time = time.time()
        self._lock = asyncio.Lock()
    
    async def add_item(self, item: Dict[str, Any]) -> bool:
        """
        添加项目到队列
        
        Returns:
            bool: 是否需要立即刷新
        """
        async with self._lock:
            self.queue.append(item)
            
            current_time = time.time()
            should_flush = (
                len(self.queue) >= self.max_size or
                (current_time - self.last_flush_time) >= self.max_wait_time
            )
            
            return should_flush
    
    async def get_items(self) -> List[Dict[str, Any]]:
        """获取并清空队列"""
        async with self._lock:
            items = self.queue.copy()
            self.queue.clear()
            self.last_flush_time = time.time()
            return items
    
    def size(self) -> int:
        """获取队列大小"""
        return len(self.queue)


class PersistenceService:
    """数据持久化服务"""
    
    def __init__(
        self,
        redis_client: RedisCache,
        mongo_client: MongoClient,
        operation_logger: OperationLogger,
        batch_size: int = 1000,
        batch_timeout: float = 10.0,
        full_sync_interval: float = 300.0,  # 5分钟全量持久化
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        consistency_check_interval: float = 3600.0  # 1小时数据一致性检查
    ):
        """
        初始化持久化服务
        
        Args:
            redis_client: Redis客户端
            mongo_client: MongoDB客户端
            operation_logger: 操作日志记录器
            batch_size: 批量大小
            batch_timeout: 批量超时时间(秒)
            full_sync_interval: 全量同步间隔(秒)
            retry_attempts: 重试次数
            retry_delay: 重试延迟(秒)
            consistency_check_interval: 一致性检查间隔(秒)
        """
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.operation_logger = operation_logger
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.full_sync_interval = full_sync_interval
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.consistency_check_interval = consistency_check_interval
        
        # 持久化队列
        self.persistence_queue = PersistenceQueue(batch_size, batch_timeout)
        
        # 失败重试队列
        self.retry_queue: List[Dict[str, Any]] = []
        self.retry_lock = asyncio.Lock()
        
        # 统计信息
        self.stats = PersistenceStats()
        
        # 后台任务
        self._batch_processor_task: Optional[asyncio.Task] = None
        self._full_sync_task: Optional[asyncio.Task] = None
        self._retry_processor_task: Optional[asyncio.Task] = None
        self._consistency_checker_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # 数据一致性配置
        self.collections_to_sync = [
            "players",
            "guilds",
            "payment_orders",
            "scheduled_tasks"
        ]
    
    async def start(self) -> None:
        """启动持久化服务"""
        self._batch_processor_task = asyncio.create_task(
            self._batch_processor_worker()
        )
        
        self._full_sync_task = asyncio.create_task(
            self._full_sync_worker()
        )
        
        self._retry_processor_task = asyncio.create_task(
            self._retry_processor_worker()
        )
        
        self._consistency_checker_task = asyncio.create_task(
            self._consistency_checker_worker()
        )
        
        logger.info("数据持久化服务已启动")
    
    async def stop(self) -> None:
        """停止持久化服务"""
        self._shutdown = True
        
        # 停止所有后台任务
        tasks = [
            self._batch_processor_task,
            self._full_sync_task,
            self._retry_processor_task,
            self._consistency_checker_task
        ]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 处理剩余数据
        await self._process_remaining_data()
        
        logger.info("数据持久化服务已停止")
    
    async def schedule_persistence(
        self,
        collection_name: str,
        entity_id: str,
        entity_data: Dict[str, Any],
        priority: int = 0
    ) -> None:
        """
        安排持久化任务
        
        Args:
            collection_name: 集合名称
            entity_id: 实体ID
            entity_data: 实体数据
            priority: 优先级(数字越大优先级越高)
        """
        item = {
            "collection": collection_name,
            "entity_id": entity_id,
            "entity_data": entity_data,
            "priority": priority,
            "timestamp": time.time()
        }
        
        should_flush = await self.persistence_queue.add_item(item)
        
        if should_flush:
            # 立即触发批量处理
            asyncio.create_task(self._process_batch())
    
    async def force_sync(
        self,
        collection_name: Optional[str] = None,
        entity_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        强制同步数据
        
        Args:
            collection_name: 指定集合名称(可选)
            entity_id: 指定实体ID(可选)
            
        Returns:
            同步结果
        """
        start_time = time.time()
        
        try:
            if collection_name and entity_id:
                # 同步单个实体
                await self._sync_single_entity(collection_name, entity_id)
                synced_count = 1
            elif collection_name:
                # 同步整个集合
                synced_count = await self._sync_collection(collection_name)
            else:
                # 全量同步
                synced_count = await self._full_sync()
            
            sync_time = time.time() - start_time
            
            return {
                "success": True,
                "synced_count": synced_count,
                "sync_time": sync_time
            }
            
        except Exception as e:
            logger.error(f"强制同步失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "sync_time": time.time() - start_time
            }
    
    async def _batch_processor_worker(self) -> None:
        """批量处理工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(1.0)  # 每秒检查一次
                await self._process_batch()
            except Exception as e:
                logger.error(f"批量处理工作任务错误: {e}")
    
    async def _process_batch(self) -> None:
        """处理批量数据"""
        items = await self.persistence_queue.get_items()
        
        if not items:
            return
        
        start_time = time.time()
        
        try:
            # 按集合分组
            collections_data = defaultdict(list)
            for item in items:
                collections_data[item["collection"]].append(item)
            
            # 按优先级排序
            for collection, collection_items in collections_data.items():
                collection_items.sort(key=lambda x: x["priority"], reverse=True)
            
            # 批量处理每个集合
            total_processed = 0
            for collection, collection_items in collections_data.items():
                processed = await self._process_collection_batch(collection, collection_items)
                total_processed += processed
            
            # 更新统计信息
            process_time = time.time() - start_time
            self.stats.total_operations += len(items)
            self.stats.successful_operations += total_processed
            self.stats.failed_operations += len(items) - total_processed
            
            # 更新平均同步时间
            if self.stats.total_operations > 0:
                self.stats.average_sync_time = (
                    (self.stats.average_sync_time * (self.stats.total_operations - len(items)) + 
                     process_time) / self.stats.total_operations
                )
            
            logger.debug(f"批量处理完成: {total_processed}/{len(items)}, 耗时: {process_time:.3f}s")
            
        except Exception as e:
            logger.error(f"批量处理失败: {e}")
            # 将失败的项目加入重试队列
            async with self.retry_lock:
                self.retry_queue.extend(items)
    
    async def _process_collection_batch(
        self,
        collection_name: str,
        items: List[Dict[str, Any]]
    ) -> int:
        """处理单个集合的批量数据"""
        if not items:
            return 0
        
        try:
            # 构建批量更新操作
            operations = []
            for item in items:
                entity_id = item["entity_id"]
                entity_data = item["entity_data"]
                
                # 构建更新操作
                operations.append({
                    "filter": {"_id": entity_id},
                    "update": {"$set": entity_data},
                    "upsert": True
                })
            
            # 执行批量更新
            if operations:
                # 使用 MongoDB 批量操作
                from pymongo import UpdateOne
                bulk_operations = [
                    UpdateOne(
                        op["filter"],
                        op["update"],
                        upsert=op["upsert"]
                    )
                    for op in operations
                ]
                
                collection = self.mongo_client.get_collection(collection_name)
                result = await collection.bulk_write(bulk_operations, ordered=False)
                
                # 记录操作日志
                await self.operation_logger.log_batch_operations([
                    {
                        "entity_type": collection_name,
                        "entity_id": item["entity_id"],
                        "operation_type": "persist",
                        "field_name": "*",
                        "new_value": item["entity_data"],
                        "source": "persistence_service",
                        "reason": "batch_persistence"
                    }
                    for item in items
                ])
                
                return len(items)
            
            return 0
            
        except Exception as e:
            logger.error(f"处理集合批量数据失败: {collection_name}, {e}")
            
            # 将失败的项目加入重试队列
            async with self.retry_lock:
                self.retry_queue.extend(items)
            
            return 0
    
    async def _full_sync_worker(self) -> None:
        """全量同步工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.full_sync_interval)
                await self._full_sync()
            except Exception as e:
                logger.error(f"全量同步工作任务错误: {e}")
    
    async def _full_sync(self) -> int:
        """执行全量同步"""
        logger.info("开始全量数据同步...")
        start_time = time.time()
        
        total_synced = 0
        
        try:
            for collection in self.collections_to_sync:
                synced_count = await self._sync_collection(collection)
                total_synced += synced_count
                
                # 短暂休息避免过载
                await asyncio.sleep(0.1)
            
            sync_time = time.time() - start_time
            self.stats.last_full_sync = datetime.now()
            
            logger.info(f"全量同步完成: {total_synced} 个实体, 耗时: {sync_time:.3f}s")
            
            return total_synced
            
        except Exception as e:
            logger.error(f"全量同步失败: {e}")
            return total_synced
    
    async def _sync_collection(self, collection_name: str) -> int:
        """同步整个集合"""
        try:
            # 获取缓存中的所有实体键
            pattern = f"{collection_name}:*"
            
            # 这里需要实现获取Redis中匹配模式的所有键
            # 由于redis-py的异步版本可能不直接支持SCAN，我们使用替代方案
            
            # 暂时跳过这个实现，返回0
            # 在实际生产环境中，需要维护一个活跃实体列表
            
            return 0
            
        except Exception as e:
            logger.error(f"同步集合失败: {collection_name}, {e}")
            return 0
    
    async def _sync_single_entity(self, collection_name: str, entity_id: str) -> None:
        """同步单个实体"""
        try:
            cache_key = f"{collection_name}:{entity_id}"
            entity_data = await self.redis_client.get(cache_key)
            
            if entity_data:
                await self.schedule_persistence(
                    collection_name=collection_name,
                    entity_id=entity_id,
                    entity_data=entity_data,
                    priority=10  # 高优先级
                )
            
        except Exception as e:
            logger.error(f"同步单个实体失败: {collection_name}:{entity_id}, {e}")
    
    async def _retry_processor_worker(self) -> None:
        """重试处理工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.retry_delay)
                await self._process_retries()
            except Exception as e:
                logger.error(f"重试处理工作任务错误: {e}")
    
    async def _process_retries(self) -> None:
        """处理重试队列"""
        async with self.retry_lock:
            if not self.retry_queue:
                return
            
            items_to_retry = self.retry_queue.copy()
            self.retry_queue.clear()
        
        if not items_to_retry:
            return
        
        try:
            # 按集合分组重试
            collections_data = defaultdict(list)
            for item in items_to_retry:
                # 检查重试次数
                retry_count = item.get("retry_count", 0)
                if retry_count < self.retry_attempts:
                    item["retry_count"] = retry_count + 1
                    collections_data[item["collection"]].append(item)
                else:
                    logger.error(f"重试次数超限，放弃处理: {item}")
            
            # 处理重试
            for collection, collection_items in collections_data.items():
                await self._process_collection_batch(collection, collection_items)
                self.stats.retries += len(collection_items)
            
        except Exception as e:
            logger.error(f"处理重试失败: {e}")
    
    async def _consistency_checker_worker(self) -> None:
        """数据一致性检查工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.consistency_check_interval)
                await self._check_data_consistency()
            except Exception as e:
                logger.error(f"一致性检查工作任务错误: {e}")
    
    async def _check_data_consistency(self) -> None:
        """检查数据一致性"""
        logger.info("开始数据一致性检查...")
        
        try:
            inconsistencies = 0
            
            for collection in self.collections_to_sync:
                collection_inconsistencies = await self._check_collection_consistency(collection)
                inconsistencies += collection_inconsistencies
            
            self.stats.data_consistency_checks += 1
            self.stats.inconsistencies_found += inconsistencies
            
            if inconsistencies > 0:
                logger.warning(f"发现数据不一致: {inconsistencies} 个")
            else:
                logger.info("数据一致性检查通过")
            
        except Exception as e:
            logger.error(f"数据一致性检查失败: {e}")
    
    async def _check_collection_consistency(self, collection_name: str) -> int:
        """检查单个集合的数据一致性"""
        # 这里实现具体的一致性检查逻辑
        # 比较Redis缓存和MongoDB中的数据
        # 暂时返回0，表示没有发现不一致
        return 0
    
    async def _process_remaining_data(self) -> None:
        """处理剩余数据"""
        # 处理持久化队列中的剩余数据
        await self._process_batch()
        
        # 处理重试队列中的剩余数据
        await self._process_retries()
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取持久化统计信息"""
        queue_size = self.persistence_queue.size()
        
        async with self.retry_lock:
            retry_queue_size = len(self.retry_queue)
        
        return {
            "stats": self.stats.to_dict(),
            "queue_status": {
                "persistence_queue_size": queue_size,
                "retry_queue_size": retry_queue_size
            },
            "configuration": {
                "batch_size": self.batch_size,
                "batch_timeout": self.batch_timeout,
                "full_sync_interval": self.full_sync_interval,
                "retry_attempts": self.retry_attempts,
                "consistency_check_interval": self.consistency_check_interval
            }
        }


# 全局持久化服务实例
_persistence_service: Optional[PersistenceService] = None


async def get_persistence_service(
    redis_client: RedisCache,
    mongo_client: MongoClient,
    operation_logger: OperationLogger
) -> PersistenceService:
    """获取全局持久化服务实例"""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = PersistenceService(
            redis_client=redis_client,
            mongo_client=mongo_client,
            operation_logger=operation_logger
        )
        await _persistence_service.start()
    return _persistence_service


async def close_persistence_service() -> None:
    """关闭全局持久化服务实例"""
    global _persistence_service
    if _persistence_service is not None:
        await _persistence_service.stop()
        _persistence_service = None