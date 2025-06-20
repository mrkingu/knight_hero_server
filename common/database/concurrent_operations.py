"""
并发操作管理
统一管理所有并发操作相关的类和功能
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, List, Optional
import asyncio
from .concurrent.operation_type import OperationType

class ConcurrentOperation:
    """并发操作对象"""
    
    def __init__(
        self,
        field: str,
        operation: OperationType,
        value: Any,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None
    ):
        """
        初始化并发操作
        
        Args:
            field: 字段名
            operation: 操作类型
            value: 操作值
            min_value: 最小值
            max_value: 最大值
        """
        self.field = field
        self.operation = operation
        self.value = value
        self.min_value = min_value
        self.max_value = max_value
        
    def check_bounds(self, current_value: Any, new_value: Any) -> bool:
        """检查值是否在边界范围内"""
        if self.min_value is not None and new_value < self.min_value:
            return False
        if self.max_value is not None and new_value > self.max_value:
            return False
        return True

class OperationQueue:
    """操作队列"""
    
    def __init__(self, entity_id: str):
        """
        初始化操作队列
        
        Args:
            entity_id: 实体ID
        """
        self.entity_id = entity_id
        self._queue: List[ConcurrentOperation] = []
        
    def add_operation(self, operation: ConcurrentOperation):
        """添加操作到队列"""
        self._queue.append(operation)
        
    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._queue) == 0
        
    def get_next_batch(self, max_size: int = 10) -> List[ConcurrentOperation]:
        """获取下一批操作"""
        batch = self._queue[:max_size]
        self._queue = self._queue[max_size:]
        return batch

class ConcurrentOperationManager:
    """并发操作管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self._queues: Dict[str, OperationQueue] = {}
        
    def add_operation(self, entity_id: str, operation: ConcurrentOperation):
        """添加操作到指定实体的队列"""
        if entity_id not in self._queues:
            self._queues[entity_id] = OperationQueue(entity_id)
        self._queues[entity_id].add_operation(operation)
        
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        total_operations = 0
        for queue in self._queues.values():
            total_operations += len(queue._queue)
            
        return {
            "total_queues": len(self._queues),
            "total_operations": total_operations
        }