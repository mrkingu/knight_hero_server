"""
并发操作定义
定义所有支持的原子操作类型
作者: lx
日期: 2025-06-18
"""
from enum import Enum
from typing import Any, Optional, Callable, Dict, List
from dataclasses import dataclass


class OperationType(Enum):
    """操作类型枚举"""
    SET = "set"              # 直接设置
    INCREMENT = "incr"       # 增加
    DECREMENT = "decr"       # 减少
    MULTIPLY = "mult"        # 乘法
    APPEND = "append"        # 追加(列表)
    REMOVE = "remove"        # 移除(列表)
    UNION = "union"          # 并集(集合)
    INTERSECT = "intersect"  # 交集(集合)


@dataclass
class ConcurrentOperation:
    """并发操作描述"""
    field: str                          # 字段名
    operation: OperationType            # 操作类型
    value: Any                          # 操作值
    validator: Optional[Callable] = None        # 验证函数
    max_value: Optional[Any] = None             # 最大值限制
    min_value: Optional[Any] = None             # 最小值限制
    rollback: Optional[Callable] = None         # 回滚函数
    
    def validate(self) -> bool:
        """验证操作是否合法"""
        if self.validator:
            return self.validator(self.value)
        return True
    
    def check_bounds(self, current_value: Any, new_value: Any) -> bool:
        """检查值是否在边界范围内"""
        if self.min_value is not None and new_value < self.min_value:
            return False
        if self.max_value is not None and new_value > self.max_value:
            return False
        return True


@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    old_value: Any = None
    new_value: Any = None
    error: Optional[str] = None
    rollback_data: Optional[Dict] = None


class OperationQueue:
    """单个实体的操作队列，保证按顺序执行"""
    
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.operations: List[ConcurrentOperation] = []
        self.is_processing = False
    
    def add_operation(self, operation: ConcurrentOperation) -> None:
        """添加操作到队列"""
        self.operations.append(operation)
    
    def get_next_batch(self, max_size: int = 10) -> List[ConcurrentOperation]:
        """获取下一批要处理的操作"""
        if not self.operations:
            return []
        
        batch_size = min(max_size, len(self.operations))
        batch = self.operations[:batch_size]
        self.operations = self.operations[batch_size:]
        return batch
    
    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self.operations) == 0


class ConcurrentOperationManager:
    """并发操作管理器，管理所有实体的操作队列"""
    
    def __init__(self):
        self.entity_queues: Dict[str, OperationQueue] = {}
        self.processing_entities: set = set()
    
    def add_operation(self, entity_id: str, operation: ConcurrentOperation) -> None:
        """为指定实体添加操作"""
        if entity_id not in self.entity_queues:
            self.entity_queues[entity_id] = OperationQueue(entity_id)
        
        self.entity_queues[entity_id].add_operation(operation)
    
    def get_next_entity_to_process(self) -> Optional[str]:
        """获取下一个要处理的实体ID"""
        for entity_id, queue in self.entity_queues.items():
            if (entity_id not in self.processing_entities and 
                not queue.is_empty()):
                return entity_id
        return None
    
    def start_processing(self, entity_id: str) -> bool:
        """标记实体开始处理"""
        if entity_id in self.processing_entities:
            return False
        self.processing_entities.add(entity_id)
        return True
    
    def finish_processing(self, entity_id: str) -> None:
        """标记实体处理完成"""
        self.processing_entities.discard(entity_id)
        
        # 如果队列为空，移除队列
        if (entity_id in self.entity_queues and 
            self.entity_queues[entity_id].is_empty()):
            del self.entity_queues[entity_id]
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            "total_queues": len(self.entity_queues),
            "processing_entities": len(self.processing_entities),
            "total_operations": sum(len(q.operations) for q in self.entity_queues.values()),
            "queue_details": {
                entity_id: len(queue.operations) 
                for entity_id, queue in self.entity_queues.items()
            }
        }