"""
数据库查询优化器
Database Query Optimizer

作者: mrkingu
日期: 2025-06-20
描述: 提供查询优化和批量操作工具，提升数据库访问性能
"""
import asyncio
from typing import List, Dict, Any, Set, Optional, Tuple
import time
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """查询优化器"""
    
    def __init__(self):
        self._batch_queries: Dict[str, List] = defaultdict(list)
        self._query_cache: Dict[str, Tuple[Any, float]] = {}
        self._indexed_fields: Dict[str, Set[str]] = {}
        self._query_stats: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "total_time": 0,
            "avg_time": 0,
            "cache_hits": 0
        })
        
    def register_collection_indexes(self, collection: str, indexes: List[str]):
        """
        注册集合的索引字段
        
        Args:
            collection: 集合名称
            indexes: 索引字段列表
        """
        self._indexed_fields[collection] = set(indexes)
        logger.debug(f"Registered indexes for {collection}: {indexes}")
        
    async def batch_get(self, collection: str, ids: List[str], cache_ttl: int = 300) -> Dict[str, Any]:
        """
        批量获取数据
        
        Args:
            collection: 集合名称
            ids: ID列表
            cache_ttl: 缓存时间
            
        Returns:
            ID到数据的映射
        """
        start_time = time.time()
        
        # 1. 先查缓存
        cached = {}
        missing_ids = []
        current_time = time.time()
        
        for doc_id in ids:
            cache_key = f"{collection}:{doc_id}"
            if cache_key in self._query_cache:
                data, expire_time = self._query_cache[cache_key]
                if current_time < expire_time:
                    cached[doc_id] = data
                    self._query_stats[collection]["cache_hits"] += 1
                else:
                    # 缓存过期
                    del self._query_cache[cache_key]
                    missing_ids.append(doc_id)
            else:
                missing_ids.append(doc_id)
        
        # 2. 批量查询缺失的
        if missing_ids:
            # 这里需要具体的数据库实现
            # 示例使用MongoDB
            try:
                # 假设有数据库客户端
                # results = await db[collection].find({"_id": {"$in": missing_ids}}).to_list(None)
                
                # 模拟查询结果
                results = []
                for doc_id in missing_ids:
                    # 这里应该是实际的数据库查询
                    result = {"_id": doc_id, "data": f"data_for_{doc_id}"}
                    results.append(result)
                
                # 缓存新查询的数据
                expire_time = current_time + cache_ttl
                for result in results:
                    doc_id = result["_id"]
                    cache_key = f"{collection}:{doc_id}"
                    self._query_cache[cache_key] = (result, expire_time)
                    cached[doc_id] = result
                    
            except Exception as e:
                logger.error(f"Batch query failed for {collection}: {e}")
                
        # 3. 更新统计
        elapsed = time.time() - start_time
        stats = self._query_stats[collection]
        stats["count"] += 1
        stats["total_time"] += elapsed
        stats["avg_time"] = stats["total_time"] / stats["count"]
        
        return cached
        
    def optimize_query(self, collection: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化查询条件
        
        Args:
            collection: 集合名称
            query: 原始查询条件
            
        Returns:
            优化后的查询条件
        """
        indexed_fields = self._indexed_fields.get(collection, set())
        
        if not indexed_fields:
            return query
        
        # 1. 重排查询条件，索引字段优先
        optimized = {}
        
        # 先添加索引字段
        for field in indexed_fields:
            if field in query:
                optimized[field] = query[field]
        
        # 再添加非索引字段
        for field, value in query.items():
            if field not in optimized:
                optimized[field] = value
        
        return optimized
        
    def build_compound_query(self, base_query: Dict[str, Any], filters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        构建复合查询
        
        Args:
            base_query: 基础查询条件
            filters: 附加过滤条件
            
        Returns:
            复合查询条件
        """
        if not filters:
            return base_query
        
        # 合并所有条件
        combined = base_query.copy()
        
        and_conditions = []
        for filter_dict in filters:
            for key, value in filter_dict.items():
                if key in combined:
                    # 如果字段已存在，使用$and操作符
                    and_conditions.append({key: combined[key]})
                    and_conditions.append({key: value})
                    del combined[key]
                else:
                    combined[key] = value
        
        if and_conditions:
            combined["$and"] = and_conditions
        
        return combined
        
    def get_query_stats(self) -> Dict[str, Any]:
        """获取查询统计信息"""
        return dict(self._query_stats)
        
    def clear_cache(self, collection: Optional[str] = None):
        """
        清理查询缓存
        
        Args:
            collection: 集合名称，为None时清理所有缓存
        """
        if collection is None:
            self._query_cache.clear()
        else:
            keys_to_remove = [key for key in self._query_cache.keys() 
                            if key.startswith(f"{collection}:")]
            for key in keys_to_remove:
                del self._query_cache[key]


class BatchProcessor:
    """批量处理器"""
    
    def __init__(self, max_batch_size: int = 1000, flush_interval: float = 1.0):
        self.max_batch_size = max_batch_size
        self.flush_interval = flush_interval
        self._insert_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._update_batches: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = defaultdict(list)
        self._delete_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._last_flush = time.time()
        
    async def add_insert(self, collection: str, document: Dict[str, Any]):
        """添加插入操作到批次"""
        self._insert_batches[collection].append(document)
        await self._check_and_flush(collection, "insert")
        
    async def add_update(self, collection: str, filter_dict: Dict[str, Any], update_dict: Dict[str, Any]):
        """添加更新操作到批次"""
        self._update_batches[collection].append((filter_dict, update_dict))
        await self._check_and_flush(collection, "update")
        
    async def add_delete(self, collection: str, filter_dict: Dict[str, Any]):
        """添加删除操作到批次"""
        self._delete_batches[collection].append(filter_dict)
        await self._check_and_flush(collection, "delete")
        
    async def _check_and_flush(self, collection: str, operation: str):
        """检查是否需要刷新批次"""
        current_time = time.time()
        
        # 检查批次大小
        if operation == "insert" and len(self._insert_batches[collection]) >= self.max_batch_size:
            await self.flush_inserts(collection)
        elif operation == "update" and len(self._update_batches[collection]) >= self.max_batch_size:
            await self.flush_updates(collection)
        elif operation == "delete" and len(self._delete_batches[collection]) >= self.max_batch_size:
            await self.flush_deletes(collection)
        
        # 检查时间间隔
        elif current_time - self._last_flush >= self.flush_interval:
            await self.flush_all()
            
    async def flush_inserts(self, collection: str):
        """刷新插入批次"""
        if not self._insert_batches[collection]:
            return
            
        documents = self._insert_batches[collection]
        self._insert_batches[collection] = []
        
        try:
            # 这里执行实际的批量插入
            # await db[collection].insert_many(documents)
            logger.debug(f"Batch inserted {len(documents)} documents to {collection}")
        except Exception as e:
            logger.error(f"Batch insert failed for {collection}: {e}")
            # 重新加入队列或处理错误
            
    async def flush_updates(self, collection: str):
        """刷新更新批次"""
        if not self._update_batches[collection]:
            return
            
        updates = self._update_batches[collection]
        self._update_batches[collection] = []
        
        try:
            # 执行批量更新
            # bulk_ops = []
            # for filter_dict, update_dict in updates:
            #     bulk_ops.append(UpdateOne(filter_dict, {"$set": update_dict}))
            # await db[collection].bulk_write(bulk_ops)
            logger.debug(f"Batch updated {len(updates)} documents in {collection}")
        except Exception as e:
            logger.error(f"Batch update failed for {collection}: {e}")
            
    async def flush_deletes(self, collection: str):
        """刷新删除批次"""
        if not self._delete_batches[collection]:
            return
            
        deletes = self._delete_batches[collection]
        self._delete_batches[collection] = []
        
        try:
            # 执行批量删除
            # if len(deletes) == 1:
            #     await db[collection].delete_many(deletes[0])
            # else:
            #     bulk_ops = [DeleteMany(filter_dict) for filter_dict in deletes]
            #     await db[collection].bulk_write(bulk_ops)
            logger.debug(f"Batch deleted {len(deletes)} filter conditions from {collection}")
        except Exception as e:
            logger.error(f"Batch delete failed for {collection}: {e}")
            
    async def flush_all(self):
        """刷新所有批次"""
        self._last_flush = time.time()
        
        # 并发执行所有刷新操作
        tasks = []
        
        for collection in self._insert_batches:
            if self._insert_batches[collection]:
                tasks.append(self.flush_inserts(collection))
                
        for collection in self._update_batches:
            if self._update_batches[collection]:
                tasks.append(self.flush_updates(collection))
                
        for collection in self._delete_batches:
            if self._delete_batches[collection]:
                tasks.append(self.flush_deletes(collection))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class ConnectionPool:
    """数据库连接池"""
    
    def __init__(self, connection_factory, min_size: int = 5, max_size: int = 20):
        self.connection_factory = connection_factory
        self.min_size = min_size
        self.max_size = max_size
        self._pool: deque = deque()
        self._active_connections: Set = set()
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """初始化连接池"""
        async with self._lock:
            for _ in range(self.min_size):
                conn = await self.connection_factory()
                self._pool.append(conn)
                
    async def acquire(self):
        """获取连接"""
        async with self._lock:
            if self._pool:
                conn = self._pool.popleft()
                self._active_connections.add(conn)
                return conn
            elif len(self._active_connections) < self.max_size:
                conn = await self.connection_factory()
                self._active_connections.add(conn)
                return conn
            else:
                # 等待连接可用
                while not self._pool:
                    await asyncio.sleep(0.01)
                
                conn = self._pool.popleft()
                self._active_connections.add(conn)
                return conn
                
    async def release(self, conn):
        """释放连接"""
        async with self._lock:
            if conn in self._active_connections:
                self._active_connections.remove(conn)
                self._pool.append(conn)
                
    async def close_all(self):
        """关闭所有连接"""
        async with self._lock:
            for conn in list(self._pool) + list(self._active_connections):
                if hasattr(conn, 'close'):
                    await conn.close()
            
            self._pool.clear()
            self._active_connections.clear()
            
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计"""
        return {
            "pool_size": len(self._pool),
            "active_connections": len(self._active_connections),
            "total_connections": len(self._pool) + len(self._active_connections),
            "max_size": self.max_size,
            "min_size": self.min_size
        }


# 全局实例
query_optimizer = QueryOptimizer()
batch_processor = BatchProcessor()


def batch_operation(operation: str, collection: str):
    """
    批量操作装饰器
    
    Args:
        operation: 操作类型 (insert/update/delete)
        collection: 集合名称
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            if operation == "insert":
                document = kwargs.get("document") or (args[0] if args else {})
                await batch_processor.add_insert(collection, document)
            elif operation == "update":
                filter_dict = kwargs.get("filter") or (args[0] if args else {})
                update_dict = kwargs.get("update") or (args[1] if len(args) > 1 else {})
                await batch_processor.add_update(collection, filter_dict, update_dict)
            elif operation == "delete":
                filter_dict = kwargs.get("filter") or (args[0] if args else {})
                await batch_processor.add_delete(collection, filter_dict)
            
            # 返回操作成功标志
            return {"success": True, "operation": operation, "collection": collection}
        
        return wrapper
    return decorator