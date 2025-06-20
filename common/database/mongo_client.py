"""
MongoDB客户端封装
提供异步操作和批量写入优化
作者: lx
日期: 2025-06-18
"""
import asyncio
import time
import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from contextlib import asynccontextmanager

import motor.motor_asyncio as motor
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import InsertOne, UpdateOne, DeleteOne, ReplaceOne
from pymongo.errors import DuplicateKeyError, BulkWriteError, ConnectionFailure
from beanie import init_beanie, Document

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Document)


class BatchWriteBuffer:
    """批量写入缓冲区"""
    
    def __init__(self, max_size: int = 1000, max_wait_time: float = 10.0):
        self.max_size = max_size
        self.max_wait_time = max_wait_time
        self.operations: List[Union[InsertOne, UpdateOne, DeleteOne, ReplaceOne]] = []
        self.last_flush_time = time.time()
        self._lock = asyncio.Lock()
    
    async def add_operation(
        self, 
        operation: Union[InsertOne, UpdateOne, DeleteOne, ReplaceOne]
    ) -> bool:
        """
        添加操作到缓冲区
        
        Returns:
            bool: 是否需要立即刷新
        """
        async with self._lock:
            self.operations.append(operation)
            
            current_time = time.time()
            should_flush = (
                len(self.operations) >= self.max_size or
                (current_time - self.last_flush_time) >= self.max_wait_time
            )
            
            return should_flush
    
    async def get_operations(self) -> List[Union[InsertOne, UpdateOne, DeleteOne, ReplaceOne]]:
        """获取并清空操作列表"""
        async with self._lock:
            operations = self.operations.copy()
            self.operations.clear()
            self.last_flush_time = time.time()
            return operations
    
    def size(self) -> int:
        """获取当前缓冲区大小"""
        return len(self.operations)


class MongoClient:
    """MongoDB客户端封装"""
    
    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        database_name: str = "knight_hero",
        max_pool_size: int = 50,
        min_pool_size: int = 10,
        max_idle_time_ms: int = 30000,
        server_selection_timeout_ms: int = 5000,
        retry_writes: bool = True,
        write_concern_w: Union[int, str] = 1,
        write_concern_journal: bool = True
    ):
        """
        初始化MongoDB客户端
        
        Args:
            uri: MongoDB连接URI
            database_name: 数据库名称
            max_pool_size: 最大连接池大小
            min_pool_size: 最小连接池大小
            max_idle_time_ms: 最大空闲时间(毫秒)
            server_selection_timeout_ms: 服务器选择超时时间(毫秒)
            retry_writes: 是否重试写入
            write_concern_w: 写确认级别
            write_concern_journal: 是否等待日志确认
        """
        self.uri = uri
        self.database_name = database_name
        
        # 创建客户端配置
        self.client_options = {
            "maxPoolSize": max_pool_size,
            "minPoolSize": min_pool_size,
            "maxIdleTimeMS": max_idle_time_ms,
            "serverSelectionTimeoutMS": server_selection_timeout_ms,
            "retryWrites": retry_writes,
            "w": write_concern_w,
            "journal": write_concern_journal
        }
        
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        
        # 批量写入缓冲区
        self.write_buffers: Dict[str, BatchWriteBuffer] = {}
        
        # 自动重连配置
        self.auto_reconnect = True
        self.reconnect_attempts = 3
        self.reconnect_delay = 1.0
        
        # 统计信息
        self.stats = {
            "insert_ops": 0,
            "update_ops": 0,
            "delete_ops": 0,
            "batch_writes": 0,
            "connection_errors": 0,
            "successful_connections": 0
        }
        
        # 后台任务
        self._batch_flush_task: Optional[asyncio.Task] = None
        self._shutdown = False
    
    async def connect(self, document_models: Optional[List[Type[Document]]] = None) -> None:
        """建立数据库连接并初始化Beanie"""
        for attempt in range(self.reconnect_attempts):
            try:
                # 创建MongoDB客户端
                self.client = AsyncIOMotorClient(self.uri, **self.client_options)
                
                # 测试连接
                await self.client.admin.command("ping")
                
                # 获取数据库
                self.database = self.client[self.database_name]
                
                # 初始化Beanie ODM
                if document_models:
                    await init_beanie(
                        database=self.database,
                        document_models=document_models
                    )
                
                # 启动批量写入任务
                self._batch_flush_task = asyncio.create_task(self._batch_flush_worker())
                
                self.stats["successful_connections"] += 1
                logger.info(f"MongoDB连接成功: {self.database_name}")
                return
                
            except Exception as e:
                self.stats["connection_errors"] += 1
                logger.error(f"MongoDB连接失败 (尝试 {attempt + 1}/{self.reconnect_attempts}): {e}")
                
                if attempt < self.reconnect_attempts - 1:
                    await asyncio.sleep(self.reconnect_delay * (attempt + 1))
                else:
                    raise ConnectionFailure(f"无法连接到MongoDB: {e}")
    
    async def disconnect(self) -> None:
        """断开数据库连接"""
        self._shutdown = True
        
        # 停止批量写入任务
        if self._batch_flush_task and not self._batch_flush_task.done():
            self._batch_flush_task.cancel()
            try:
                await self._batch_flush_task
            except asyncio.CancelledError:
                pass
        
        # 刷新所有待写入数据
        await self._flush_all_buffers()
        
        # 关闭客户端连接
        if self.client:
            self.client.close()
            self.client = None
            self.database = None
        
        logger.info("MongoDB连接已断开")
    
    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection:
        """获取集合对象"""
        if not self.database:
            raise RuntimeError("数据库未连接")
        return self.database[collection_name]
    
    async def create_indexes(self, collection_name: str, indexes: List[Dict]) -> None:
        """创建索引"""
        try:
            collection = self.get_collection(collection_name)
            
            for index_spec in indexes:
                if isinstance(index_spec, dict) and "keys" in index_spec:
                    await collection.create_index(
                        index_spec["keys"],
                        **{k: v for k, v in index_spec.items() if k != "keys"}
                    )
                else:
                    # 简单索引格式
                    await collection.create_index(index_spec)
            
            logger.info(f"为集合 {collection_name} 创建了 {len(indexes)} 个索引")
            
        except Exception as e:
            logger.error(f"创建索引失败: {collection_name}, {e}")
            raise
    
    async def insert_one(
        self, 
        collection_name: str, 
        document: Dict[str, Any],
        use_buffer: bool = True
    ) -> Optional[str]:
        """插入单个文档"""
        if use_buffer:
            operation = InsertOne(document)
            should_flush = await self._add_to_buffer(collection_name, operation)
            
            if should_flush:
                await self._flush_buffer(collection_name)
            
            return None  # 批量插入时无法立即返回ID
        else:
            try:
                collection = self.get_collection(collection_name)
                result = await collection.insert_one(document)
                self.stats["insert_ops"] += 1
                return str(result.inserted_id)
            except Exception as e:
                logger.error(f"插入文档失败: {collection_name}, {e}")
                raise
    
    async def insert_many(
        self, 
        collection_name: str, 
        documents: List[Dict[str, Any]],
        ordered: bool = False
    ) -> List[str]:
        """批量插入文档"""
        try:
            collection = self.get_collection(collection_name)
            result = await collection.insert_many(documents, ordered=ordered)
            self.stats["insert_ops"] += len(documents)
            return [str(oid) for oid in result.inserted_ids]
        except Exception as e:
            logger.error(f"批量插入失败: {collection_name}, {e}")
            raise
    
    async def update_one(
        self,
        collection_name: str,
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any],
        upsert: bool = False,
        use_buffer: bool = True
    ) -> bool:
        """更新单个文档"""
        if use_buffer:
            operation = UpdateOne(filter_dict, update_dict, upsert=upsert)
            should_flush = await self._add_to_buffer(collection_name, operation)
            
            if should_flush:
                await self._flush_buffer(collection_name)
            
            return True
        else:
            try:
                collection = self.get_collection(collection_name)
                result = await collection.update_one(filter_dict, update_dict, upsert=upsert)
                self.stats["update_ops"] += 1
                return result.modified_count > 0 or (upsert and result.upserted_id)
            except Exception as e:
                logger.error(f"更新文档失败: {collection_name}, {e}")
                raise
    
    async def update_many(
        self,
        collection_name: str,
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any]
    ) -> int:
        """批量更新文档"""
        try:
            collection = self.get_collection(collection_name)
            result = await collection.update_many(filter_dict, update_dict)
            self.stats["update_ops"] += result.modified_count
            return result.modified_count
        except Exception as e:
            logger.error(f"批量更新失败: {collection_name}, {e}")
            raise
    
    async def delete_one(
        self,
        collection_name: str,
        filter_dict: Dict[str, Any],
        use_buffer: bool = True
    ) -> bool:
        """删除单个文档"""
        if use_buffer:
            operation = DeleteOne(filter_dict)
            should_flush = await self._add_to_buffer(collection_name, operation)
            
            if should_flush:
                await self._flush_buffer(collection_name)
            
            return True
        else:
            try:
                collection = self.get_collection(collection_name)
                result = await collection.delete_one(filter_dict)
                self.stats["delete_ops"] += 1
                return result.deleted_count > 0
            except Exception as e:
                logger.error(f"删除文档失败: {collection_name}, {e}")
                raise
    
    async def find_one(
        self,
        collection_name: str,
        filter_dict: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """查找单个文档"""
        try:
            collection = self.get_collection(collection_name)
            return await collection.find_one(filter_dict or {}, projection)
        except Exception as e:
            logger.error(f"查找文档失败: {collection_name}, {e}")
            raise
    
    async def find_many(
        self,
        collection_name: str,
        filter_dict: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """查找多个文档"""
        try:
            collection = self.get_collection(collection_name)
            cursor = collection.find(filter_dict or {}, projection)
            
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"查找文档失败: {collection_name}, {e}")
            raise
    
    async def count_documents(
        self,
        collection_name: str,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> int:
        """统计文档数量"""
        try:
            collection = self.get_collection(collection_name)
            return await collection.count_documents(filter_dict or {})
        except Exception as e:
            logger.error(f"统计文档失败: {collection_name}, {e}")
            raise
    
    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        if not self.client:
            raise RuntimeError("数据库未连接")
        
        async with await self.client.start_session() as session:
            async with session.start_transaction():
                yield session
    
    async def _add_to_buffer(
        self, 
        collection_name: str, 
        operation: Union[InsertOne, UpdateOne, DeleteOne, ReplaceOne]
    ) -> bool:
        """添加操作到缓冲区"""
        if collection_name not in self.write_buffers:
            self.write_buffers[collection_name] = BatchWriteBuffer()
        
        return await self.write_buffers[collection_name].add_operation(operation)
    
    async def _flush_buffer(self, collection_name: str) -> None:
        """刷新指定集合的缓冲区"""
        if collection_name not in self.write_buffers:
            return
        
        buffer = self.write_buffers[collection_name]
        operations = await buffer.get_operations()
        
        if not operations:
            return
        
        try:
            collection = self.get_collection(collection_name)
            result = await collection.bulk_write(operations, ordered=False)
            
            self.stats["batch_writes"] += 1
            self.stats["insert_ops"] += len(result.inserted_ids) if result.inserted_ids else 0
            self.stats["update_ops"] += result.modified_count
            self.stats["delete_ops"] += result.deleted_count
            
            logger.debug(
                f"批量写入完成: {collection_name}, "
                f"操作数: {len(operations)}, "
                f"插入: {len(result.inserted_ids) if result.inserted_ids else 0}, "
                f"更新: {result.modified_count}, "
                f"删除: {result.deleted_count}"
            )
            
        except BulkWriteError as e:
            logger.error(f"批量写入部分失败: {collection_name}, {e.details}")
            # 重新处理失败的操作
            await self._handle_bulk_write_errors(collection_name, e)
        except Exception as e:
            logger.error(f"批量写入失败: {collection_name}, {e}")
            raise
    
    async def _flush_all_buffers(self) -> None:
        """刷新所有缓冲区"""
        for collection_name in list(self.write_buffers.keys()):
            try:
                await self._flush_buffer(collection_name)
            except Exception as e:
                logger.error(f"刷新缓冲区失败: {collection_name}, {e}")
    
    async def _batch_flush_worker(self) -> None:
        """批量刷新工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(1.0)  # 每秒检查一次
                
                for collection_name, buffer in list(self.write_buffers.items()):
                    current_time = time.time()
                    if (current_time - buffer.last_flush_time) >= buffer.max_wait_time:
                        await self._flush_buffer(collection_name)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"批量刷新工作任务错误: {e}")
    
    async def _handle_bulk_write_errors(
        self, 
        collection_name: str, 
        bulk_error: BulkWriteError
    ) -> None:
        """处理批量写入错误"""
        # 这里可以实现重试逻辑或错误恢复策略
        write_errors = bulk_error.details.get("writeErrors", [])
        
        for error in write_errors:
            if error["code"] == 11000:  # 重复键错误
                logger.warning(f"重复键错误: {collection_name}, {error}")
            else:
                logger.error(f"写入错误: {collection_name}, {error}")
    
    async def force_flush(self, collection_name: Optional[str] = None) -> None:
        """强制刷新缓冲区"""
        if collection_name:
            await self._flush_buffer(collection_name)
        else:
            await self._flush_all_buffers()
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息"""
        buffer_stats = {}
        for collection_name, buffer in self.write_buffers.items():
            buffer_stats[collection_name] = {
                "pending_operations": buffer.size(),
                "last_flush_time": buffer.last_flush_time
            }
        
        return {
            "operations": self.stats.copy(),
            "buffers": buffer_stats,
            "connection_info": {
                "database_name": self.database_name,
                "connected": self.client is not None and self.database is not None
            }
        }
    
    async def clear_stats(self) -> None:
        """清空统计信息"""
        self.stats = {
            "insert_ops": 0,
            "update_ops": 0,
            "delete_ops": 0,
            "batch_writes": 0,
            "connection_errors": 0,
            "successful_connections": 0
        }


# 全局MongoDB客户端实例
_mongo_client: Optional[MongoClient] = None


async def get_mongo_client() -> MongoClient:
    """获取全局MongoDB客户端实例"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient()
    return _mongo_client


async def close_mongo_client() -> None:
    """关闭全局MongoDB客户端实例"""
    global _mongo_client
    if _mongo_client is not None:
        await _mongo_client.disconnect()
        _mongo_client = None