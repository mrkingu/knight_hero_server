"""
消息队列模块  
Message Queue Module

作者: lx
日期: 2025-06-18
描述: 实现优先级队列、背压控制、队列监控、消息去重
"""
import asyncio
import time
import heapq
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
from collections import deque

from common.protocol.core.base_request import BaseRequest


class MessagePriority(IntEnum):
    """消息优先级枚举 (数值越小优先级越高)"""
    CRITICAL = 0    # 关键消息 (系统消息、错误处理)
    HIGH = 1        # 高优先级 (实时战斗、支付)
    NORMAL = 2      # 普通优先级 (聊天、查询)
    LOW = 3         # 低优先级 (日志、统计)


@dataclass
class QueuedMessage:
    """队列中的消息"""
    message: BaseRequest
    priority: MessagePriority
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3
    
    def __lt__(self, other):
        """优先级比较 (用于堆排序)"""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp
    
    @property
    def message_id(self) -> str:
        """获取消息唯一标识"""
        msg_id = getattr(self.message, 'msg_id', 0)
        sequence = getattr(self.message, 'sequence', '')
        return f"{msg_id}:{sequence}"
    
    @property
    def message_hash(self) -> str:
        """获取消息内容哈希 (用于去重)"""
        content = f"{self.message_id}:{getattr(self.message, 'player_id', '')}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


class BackpressureController:
    """背压控制器"""
    
    def __init__(self, 
                 max_queue_size: int = 10000,
                 high_watermark: float = 0.8,
                 low_watermark: float = 0.6,
                 drop_threshold: float = 0.95):
        """
        初始化背压控制器
        
        Args:
            max_queue_size: 最大队列大小
            high_watermark: 高水位线 (开始限流)
            low_watermark: 低水位线 (停止限流)  
            drop_threshold: 丢弃阈值 (开始丢弃低优先级消息)
        """
        self.max_queue_size = max_queue_size
        self.high_watermark = high_watermark
        self.low_watermark = low_watermark  
        self.drop_threshold = drop_threshold
        
        self._current_size = 0
        self._is_throttling = False
        self._throttle_start_time = 0.0
        
        # 统计信息
        self._stats = {
            'total_messages': 0,
            'dropped_messages': 0,
            'throttled_messages': 0,
            'throttle_duration': 0.0
        }
    
    def should_accept_message(self, priority: MessagePriority) -> bool:
        """
        判断是否应该接受消息
        
        Args:
            priority: 消息优先级
            
        Returns:
            是否接受消息
        """
        usage_ratio = self._current_size / self.max_queue_size
        
        # 超过丢弃阈值时，只接受关键消息
        if usage_ratio >= self.drop_threshold:
            return priority == MessagePriority.CRITICAL
        
        # 超过高水位线时，开始限流
        if usage_ratio >= self.high_watermark:
            if not self._is_throttling:
                self._is_throttling = True
                self._throttle_start_time = time.time()
            
            # 限流期间只接受高优先级消息
            return priority <= MessagePriority.HIGH
        
        # 低于低水位线时，停止限流
        if usage_ratio <= self.low_watermark and self._is_throttling:
            self._is_throttling = False
            self._stats['throttle_duration'] += time.time() - self._throttle_start_time
        
        return True
    
    def on_message_added(self) -> None:
        """消息添加回调"""
        self._current_size += 1
        self._stats['total_messages'] += 1
    
    def on_message_removed(self) -> None:
        """消息移除回调"""
        self._current_size = max(0, self._current_size - 1)
    
    def on_message_dropped(self) -> None:
        """消息丢弃回调"""
        self._stats['dropped_messages'] += 1
    
    def on_message_throttled(self) -> None:
        """消息限流回调"""
        self._stats['throttled_messages'] += 1
    
    @property
    def usage_ratio(self) -> float:
        """获取队列使用率"""
        return self._current_size / self.max_queue_size
    
    @property
    def is_throttling(self) -> bool:
        """是否正在限流"""
        return self._is_throttling
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self._stats.copy()
        stats.update({
            'current_size': self._current_size,
            'max_size': self.max_queue_size,
            'usage_ratio': self.usage_ratio,
            'is_throttling': self._is_throttling
        })
        return stats


class MessageDeduplicator:
    """消息去重器"""
    
    def __init__(self, window_size: int = 10000, ttl: int = 300):
        """
        初始化消息去重器
        
        Args:
            window_size: 去重窗口大小
            ttl: 消息存活时间(秒)
        """
        self.window_size = window_size
        self.ttl = ttl
        
        # 使用双端队列维护时间窗口
        self._message_hashes: deque = deque()
        self._hash_timestamps: Dict[str, float] = {}
        self._hash_set: Set[str] = set()
    
    def is_duplicate(self, message: QueuedMessage) -> bool:
        """
        检查消息是否重复
        
        Args:
            message: 待检查的消息
            
        Returns:
            是否为重复消息
        """
        self._cleanup_expired()
        
        message_hash = message.message_hash
        
        if message_hash in self._hash_set:
            return True
        
        # 添加新消息哈希
        self._add_hash(message_hash)
        return False
    
    def _add_hash(self, message_hash: str) -> None:
        """添加消息哈希"""
        current_time = time.time()
        
        # 检查是否需要移除旧消息
        if len(self._message_hashes) >= self.window_size:
            self._remove_oldest()
        
        self._message_hashes.append(message_hash)
        self._hash_timestamps[message_hash] = current_time
        self._hash_set.add(message_hash)
    
    def _remove_oldest(self) -> None:
        """移除最旧的消息哈希"""
        if self._message_hashes:
            old_hash = self._message_hashes.popleft()
            self._hash_timestamps.pop(old_hash, None)
            self._hash_set.discard(old_hash)
    
    def _cleanup_expired(self) -> None:
        """清理过期的消息哈希"""
        current_time = time.time()
        
        # 从队列前端移除过期消息
        while (self._message_hashes and 
               self._hash_timestamps.get(self._message_hashes[0], 0) + self.ttl < current_time):
            self._remove_oldest()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取去重统计信息"""
        return {
            'window_size': len(self._message_hashes),
            'max_window_size': self.window_size,
            'hash_count': len(self._hash_set)
        }


class PriorityMessageQueue:
    """优先级消息队列"""
    
    def __init__(self, 
                 max_size: int = 10000,
                 enable_deduplication: bool = True,
                 enable_backpressure: bool = True):
        """
        初始化优先级消息队列
        
        Args:
            max_size: 最大队列大小
            enable_deduplication: 是否启用消息去重
            enable_backpressure: 是否启用背压控制
        """
        # 优先级队列 (最小堆)
        self._heap: List[QueuedMessage] = []
        self._queue_lock = asyncio.Lock()
        
        # 背压控制
        self._backpressure = BackpressureController(max_size) if enable_backpressure else None
        
        # 消息去重
        self._deduplicator = MessageDeduplicator() if enable_deduplication else None
        
        # 队列监控
        self._monitor_stats = {
            'enqueue_count': 0,
            'dequeue_count': 0,
            'duplicate_count': 0,
            'rejected_count': 0,
            'retry_count': 0
        }
        
        # 等待条件
        self._not_empty = asyncio.Condition()
    
    async def enqueue(self, message: BaseRequest, priority: MessagePriority = MessagePriority.NORMAL) -> bool:
        """
        入队消息
        
        Args:
            message: 待入队的消息
            priority: 消息优先级
            
        Returns:
            是否成功入队
        """
        queued_message = QueuedMessage(
            message=message,
            priority=priority,
            timestamp=time.time()
        )
        
        # 背压控制检查
        if self._backpressure and not self._backpressure.should_accept_message(priority):
            self._monitor_stats['rejected_count'] += 1
            if self._backpressure.is_throttling:
                self._backpressure.on_message_throttled()
            else:
                self._backpressure.on_message_dropped()
            return False
        
        # 消息去重检查
        if self._deduplicator and self._deduplicator.is_duplicate(queued_message):
            self._monitor_stats['duplicate_count'] += 1
            return False
        
        async with self._queue_lock:
            # 添加到优先级队列
            heapq.heappush(self._heap, queued_message)
            
            # 更新统计
            self._monitor_stats['enqueue_count'] += 1
            if self._backpressure:
                self._backpressure.on_message_added()
        
        # 通知等待的消费者
        async with self._not_empty:
            self._not_empty.notify()
        
        return True
    
    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueuedMessage]:
        """
        出队消息
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            出队的消息，超时或队列为空返回None
        """
        try:
            # 等待队列不为空
            async with self._not_empty:
                while not self._heap:
                    await asyncio.wait_for(self._not_empty.wait(), timeout)
                
                async with self._queue_lock:
                    if self._heap:
                        queued_message = heapq.heappop(self._heap)
                        
                        # 更新统计
                        self._monitor_stats['dequeue_count'] += 1
                        if self._backpressure:
                            self._backpressure.on_message_removed()
                        
                        return queued_message
                    
        except asyncio.TimeoutError:
            pass
        
        return None
    
    async def retry_message(self, queued_message: QueuedMessage) -> bool:
        """
        重试消息
        
        Args:
            queued_message: 需要重试的消息
            
        Returns:
            是否成功重新入队
        """
        if queued_message.retry_count >= queued_message.max_retries:
            return False
        
        queued_message.retry_count += 1
        queued_message.timestamp = time.time()  # 更新时间戳
        
        async with self._queue_lock:
            heapq.heappush(self._heap, queued_message)
            self._monitor_stats['retry_count'] += 1
            if self._backpressure:
                self._backpressure.on_message_added()
        
        async with self._not_empty:
            self._not_empty.notify()
        
        return True
    
    def size(self) -> int:
        """获取队列大小"""
        return len(self._heap)
    
    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._heap) == 0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        stats = {
            'queue': {
                'size': self.size(),
                'monitor': self._monitor_stats.copy()
            }
        }
        
        if self._backpressure:
            stats['backpressure'] = self._backpressure.get_stats()
        
        if self._deduplicator:
            stats['deduplication'] = self._deduplicator.get_stats()
        
        return stats
    
    async def clear(self) -> int:
        """清空队列"""
        async with self._queue_lock:
            cleared_count = len(self._heap)
            self._heap.clear()
            
            if self._backpressure:
                # 重置背压控制器状态
                self._backpressure._current_size = 0
            
            return cleared_count


class MessageQueueManager:
    """消息队列管理器"""
    
    def __init__(self):
        """初始化消息队列管理器"""
        self._queues: Dict[str, PriorityMessageQueue] = {}
        self._default_queue = "default"
        
        # 创建默认队列
        self._queues[self._default_queue] = PriorityMessageQueue()
    
    def create_queue(self, name: str, **kwargs) -> PriorityMessageQueue:
        """
        创建命名队列
        
        Args:
            name: 队列名称
            **kwargs: 队列配置参数
            
        Returns:
            创建的消息队列
        """
        if name in self._queues:
            raise ValueError(f"队列 {name} 已存在")
        
        self._queues[name] = PriorityMessageQueue(**kwargs)
        return self._queues[name]
    
    def get_queue(self, name: str = None) -> Optional[PriorityMessageQueue]:
        """
        获取指定队列
        
        Args:
            name: 队列名称，为空则返回默认队列
            
        Returns:
            消息队列实例
        """
        queue_name = name or self._default_queue
        return self._queues.get(queue_name)
    
    def remove_queue(self, name: str) -> bool:
        """
        移除指定队列
        
        Args:
            name: 队列名称
            
        Returns:
            是否成功移除
        """
        if name == self._default_queue:
            raise ValueError("不能移除默认队列")
        
        if name in self._queues:
            del self._queues[name]
            return True
        return False
    
    def list_queues(self) -> List[str]:
        """列出所有队列名称"""
        return list(self._queues.keys())
    
    def get_total_stats(self) -> Dict[str, Any]:
        """获取所有队列的统计信息"""
        total_stats = {}
        
        for queue_name, queue in self._queues.items():
            total_stats[queue_name] = queue.get_stats()
        
        return total_stats