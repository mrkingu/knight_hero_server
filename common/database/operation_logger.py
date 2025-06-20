"""
操作日志记录器
记录所有数据修改操作，用于审计和问题追踪
作者: lx
日期: 2025-06-18
"""
import asyncio
import time
import uuid
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from collections import deque

from .models import OperationLog
from .mongo_client import MongoClient

logger = logging.getLogger(__name__)


class LogEntry:
    """日志条目"""
    
    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        operation_type: str,
        field_name: str,
        old_value: Any = None,
        new_value: Any = None,
        source: str = "",
        reason: str = "",
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.log_id = str(uuid.uuid4())
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.operation_type = operation_type
        self.field_name = field_name
        self.old_value = old_value
        self.new_value = new_value
        self.source = source
        self.reason = reason
        self.operator_id = operator_id
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "log_id": self.log_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "operation_type": self.operation_type,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "source": self.source,
            "reason": self.reason,
            "operator_id": self.operator_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


class OperationLogger:
    """操作日志记录器"""
    
    def __init__(
        self,
        mongo_client: MongoClient,
        buffer_size: int = 1000,
        flush_interval: float = 10.0,
        compression_enabled: bool = True,
        retention_days: int = 90
    ):
        """
        初始化操作日志记录器
        
        Args:
            mongo_client: MongoDB客户端
            buffer_size: 缓冲区大小
            flush_interval: 刷新间隔(秒)
            compression_enabled: 是否启用压缩
            retention_days: 日志保留天数
        """
        self.mongo_client = mongo_client
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.compression_enabled = compression_enabled
        self.retention_days = retention_days
        
        # 日志缓冲区
        self.log_buffer: deque = deque()
        self.buffer_lock = asyncio.Lock()
        
        # 后台任务
        self._flush_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
        # 统计信息
        self.stats = {
            "logs_written": 0,
            "logs_buffered": 0,
            "flush_operations": 0,
            "cleanup_operations": 0,
            "errors": 0
        }
        
        # 压缩配置
        self.compression_threshold = 1000  # 值长度超过此阈值时进行压缩
    
    async def start(self) -> None:
        """启动日志记录器"""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_worker())
        
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())
        
        logger.info("操作日志记录器已启动")
    
    async def stop(self) -> None:
        """停止日志记录器"""
        self._shutdown = True
        
        # 停止后台任务
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 刷新剩余日志
        await self._flush_logs()
        
        logger.info("操作日志记录器已停止")
    
    async def log_operation(
        self,
        entity_type: str,
        entity_id: str,
        operation_type: str,
        field_name: str,
        old_value: Any = None,
        new_value: Any = None,
        source: str = "",
        reason: str = "",
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        记录操作日志
        
        Returns:
            str: 日志ID
        """
        try:
            entry = LogEntry(
                entity_type=entity_type,
                entity_id=entity_id,
                operation_type=operation_type,
                field_name=field_name,
                old_value=self._compress_value(old_value),
                new_value=self._compress_value(new_value),
                source=source,
                reason=reason,
                operator_id=operator_id,
                metadata=metadata
            )
            
            async with self.buffer_lock:
                self.log_buffer.append(entry)
                self.stats["logs_buffered"] += 1
                
                # 如果缓冲区已满，立即刷新
                if len(self.log_buffer) >= self.buffer_size:
                    asyncio.create_task(self._flush_logs())
            
            return entry.log_id
            
        except Exception as e:
            logger.error(f"记录操作日志失败: {e}")
            self.stats["errors"] += 1
            return ""
    
    async def log_batch_operations(self, operations: List[Dict[str, Any]]) -> List[str]:
        """批量记录操作日志"""
        log_ids = []
        
        try:
            entries = []
            for op in operations:
                entry = LogEntry(
                    entity_type=op["entity_type"],
                    entity_id=op["entity_id"],
                    operation_type=op["operation_type"],
                    field_name=op["field_name"],
                    old_value=self._compress_value(op.get("old_value")),
                    new_value=self._compress_value(op.get("new_value")),
                    source=op.get("source", ""),
                    reason=op.get("reason", ""),
                    operator_id=op.get("operator_id"),
                    metadata=op.get("metadata")
                )
                entries.append(entry)
                log_ids.append(entry.log_id)
            
            async with self.buffer_lock:
                self.log_buffer.extend(entries)
                self.stats["logs_buffered"] += len(entries)
                
                # 如果缓冲区已满，立即刷新
                if len(self.log_buffer) >= self.buffer_size:
                    asyncio.create_task(self._flush_logs())
            
            return log_ids
            
        except Exception as e:
            logger.error(f"批量记录操作日志失败: {e}")
            self.stats["errors"] += 1
            return []
    
    async def get_operation_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
        skip: int = 0,
        operation_type: Optional[str] = None,
        field_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """获取操作历史"""
        try:
            filter_dict = {
                "entity_type": entity_type,
                "entity_id": entity_id
            }
            
            if operation_type:
                filter_dict["operation_type"] = operation_type
            
            if field_name:
                filter_dict["field_name"] = field_name
            
            if start_time or end_time:
                time_filter = {}
                if start_time:
                    time_filter["$gte"] = start_time
                if end_time:
                    time_filter["$lte"] = end_time
                filter_dict["timestamp"] = time_filter
            
            results = await self.mongo_client.find_many(
                collection_name="operation_logs",
                filter_dict=filter_dict,
                sort=[("timestamp", -1)],
                limit=limit,
                skip=skip
            )
            
            # 解压缩值
            for result in results:
                result["old_value"] = self._decompress_value(result.get("old_value"))
                result["new_value"] = self._decompress_value(result.get("new_value"))
            
            return results
            
        except Exception as e:
            logger.error(f"获取操作历史失败: {e}")
            return []
    
    async def generate_audit_report(
        self,
        start_time: datetime,
        end_time: datetime,
        entity_types: Optional[List[str]] = None,
        operation_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """生成审计报告"""
        try:
            filter_dict = {
                "timestamp": {
                    "$gte": start_time,
                    "$lte": end_time
                }
            }
            
            if entity_types:
                filter_dict["entity_type"] = {"$in": entity_types}
            
            if operation_types:
                filter_dict["operation_type"] = {"$in": operation_types}
            
            # 聚合统计
            pipeline = [
                {"$match": filter_dict},
                {
                    "$group": {
                        "_id": {
                            "entity_type": "$entity_type",
                            "operation_type": "$operation_type",
                            "source": "$source"
                        },
                        "count": {"$sum": 1},
                        "unique_entities": {"$addToSet": "$entity_id"},
                        "unique_operators": {"$addToSet": "$operator_id"}
                    }
                },
                {
                    "$project": {
                        "entity_type": "$_id.entity_type",
                        "operation_type": "$_id.operation_type",
                        "source": "$_id.source",
                        "count": 1,
                        "unique_entity_count": {"$size": "$unique_entities"},
                        "unique_operator_count": {"$size": "$unique_operators"}
                    }
                }
            ]
            
            collection = self.mongo_client.get_collection("operation_logs")
            results = await collection.aggregate(pipeline).to_list(length=None)
            
            # 生成报告
            report = {
                "time_range": {
                    "start": start_time,
                    "end": end_time
                },
                "summary": {
                    "total_operations": sum(r["count"] for r in results),
                    "unique_entities": len(set(r["entity_type"] + ":" + str(r["unique_entity_count"]) for r in results)),
                    "operation_breakdown": {}
                },
                "details": results
            }
            
            # 操作类型分组统计
            for result in results:
                op_type = result["operation_type"]
                if op_type not in report["summary"]["operation_breakdown"]:
                    report["summary"]["operation_breakdown"][op_type] = 0
                report["summary"]["operation_breakdown"][op_type] += result["count"]
            
            return report
            
        except Exception as e:
            logger.error(f"生成审计报告失败: {e}")
            return {}
    
    async def rollback_operations(
        self,
        entity_type: str,
        entity_id: str,
        rollback_point: datetime,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """回滚操作到指定时间点"""
        try:
            # 获取需要回滚的操作
            operations = await self.get_operation_history(
                entity_type=entity_type,
                entity_id=entity_id,
                limit=10000,  # 足够大的数量
                start_time=rollback_point
            )
            
            # 按时间逆序排列(最新的先回滚)
            operations.sort(key=lambda x: x["timestamp"], reverse=True)
            
            rollback_plan = []
            for op in operations:
                if op["operation_type"] in ["incr", "decr", "set"]:
                    rollback_plan.append({
                        "field": op["field_name"],
                        "current_value": op["new_value"],
                        "rollback_value": op["old_value"],
                        "operation": "set"
                    })
            
            result = {
                "rollback_point": rollback_point,
                "operations_to_rollback": len(rollback_plan),
                "rollback_plan": rollback_plan,
                "dry_run": dry_run
            }
            
            if not dry_run:
                # 实际执行回滚
                # 这里需要调用Repository的方法来执行回滚
                # 暂时只返回计划
                result["status"] = "planned"
            else:
                result["status"] = "dry_run_completed"
            
            return result
            
        except Exception as e:
            logger.error(f"回滚操作失败: {e}")
            return {"error": str(e)}
    
    def _compress_value(self, value: Any) -> Any:
        """压缩值"""
        if not self.compression_enabled:
            return value
        
        try:
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, ensure_ascii=False)
                if len(serialized) > self.compression_threshold:
                    import gzip
                    compressed = gzip.compress(serialized.encode('utf-8'))
                    return {
                        "_compressed": True,
                        "_data": compressed.hex()
                    }
                return value
            return value
        except Exception:
            return value
    
    def _decompress_value(self, value: Any) -> Any:
        """解压缩值"""
        if not isinstance(value, dict) or not value.get("_compressed"):
            return value
        
        try:
            import gzip
            compressed_data = bytes.fromhex(value["_data"])
            decompressed = gzip.decompress(compressed_data)
            return json.loads(decompressed.decode('utf-8'))
        except Exception:
            return value
    
    async def _flush_logs(self) -> None:
        """刷新日志到数据库"""
        if not self.log_buffer:
            return
        
        try:
            async with self.buffer_lock:
                # 取出所有待写入的日志
                logs_to_write = list(self.log_buffer)
                self.log_buffer.clear()
            
            if not logs_to_write:
                return
            
            # 批量写入数据库
            documents = [log.to_dict() for log in logs_to_write]
            await self.mongo_client.insert_many(
                collection_name="operation_logs",
                documents=documents,
                ordered=False
            )
            
            self.stats["logs_written"] += len(documents)
            self.stats["flush_operations"] += 1
            
            logger.debug(f"刷新操作日志: {len(documents)} 条")
            
        except Exception as e:
            logger.error(f"刷新日志失败: {e}")
            self.stats["errors"] += 1
            
            # 失败时将日志重新放回缓冲区
            async with self.buffer_lock:
                self.log_buffer.extendleft(reversed(logs_to_write))
    
    async def _flush_worker(self) -> None:
        """定时刷新工作任务"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"刷新工作任务错误: {e}")
                self.stats["errors"] += 1
    
    async def _cleanup_worker(self) -> None:
        """定期清理过期日志"""
        cleanup_interval = 3600  # 每小时清理一次
        
        while not self._shutdown:
            try:
                await asyncio.sleep(cleanup_interval)
                await self._cleanup_old_logs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理工作任务错误: {e}")
                self.stats["errors"] += 1
    
    async def _cleanup_old_logs(self) -> None:
        """清理过期日志"""
        try:
            cutoff_time = datetime.now() - timedelta(days=self.retention_days)
            
            result = await self.mongo_client.get_collection("operation_logs").delete_many({
                "timestamp": {"$lt": cutoff_time}
            })
            
            if result.deleted_count > 0:
                logger.info(f"清理过期日志: {result.deleted_count} 条")
                self.stats["cleanup_operations"] += 1
            
        except Exception as e:
            logger.error(f"清理过期日志失败: {e}")
            self.stats["errors"] += 1
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        async with self.buffer_lock:
            buffer_size = len(self.log_buffer)
        
        return {
            "stats": self.stats.copy(),
            "buffer_size": buffer_size,
            "buffer_capacity": self.buffer_size,
            "compression_enabled": self.compression_enabled,
            "retention_days": self.retention_days
        }


# 全局日志记录器实例
_logger_instance: Optional[OperationLogger] = None


async def get_operation_logger(mongo_client: MongoClient) -> OperationLogger:
    """获取全局操作日志记录器实例"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = OperationLogger(mongo_client)
        await _logger_instance.start()
    return _logger_instance


async def close_operation_logger() -> None:
    """关闭全局操作日志记录器实例"""
    global _logger_instance
    if _logger_instance is not None:
        await _logger_instance.stop()
        _logger_instance = None