"""
消息对象池
高性能的对象池管理，减少GC压力
作者: lx
日期: 2025-06-18
"""
from typing import Type, TypeVar, Generic, Optional, List, Dict, Any
from threading import Lock
import time

T = TypeVar('T')

class MessagePool(Generic[T]):
    """消息对象池"""
    
    def __init__(self, object_type: Type[T], max_size: int = 100):
        self.object_type = object_type
        self.max_size = max_size
        self._pool: List[T] = []
        self._lock = Lock()
        self._stats = {
            "created": 0,
            "reused": 0,
            "peak_size": 0
        }
        
    def get(self) -> T:
        """获取对象"""
        with self._lock:
            if self._pool:
                obj = self._pool.pop()
                self._stats["reused"] += 1
                return obj
            else:
                obj = self.object_type()
                self._stats["created"] += 1
                return obj
                
    def put(self, obj: T):
        """归还对象"""
        if not isinstance(obj, self.object_type):
            return
            
        with self._lock:
            if len(self._pool) < self.max_size:
                # 重置对象状态
                if hasattr(obj, 'clear'):
                    obj.clear()
                elif hasattr(obj, '__dict__'):
                    obj.__dict__.clear()
                    
                self._pool.append(obj)
                self._stats["peak_size"] = max(self._stats["peak_size"], len(self._pool))
                
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "current_size": len(self._pool),
                "max_size": self.max_size,
                "objects_created": self._stats["created"],
                "objects_reused": self._stats["reused"],
                "peak_size": self._stats["peak_size"]
            }

class BufferPool:
    """缓冲区池"""
    
    def __init__(self, initial_size: int = 1024, max_size: int = 50):
        self.initial_size = initial_size
        self.max_size = max_size
        self._pool: List[bytearray] = []
        self._lock = Lock()
        
    def get(self, min_size: int = 0) -> bytearray:
        """获取缓冲区"""
        min_size = max(min_size, self.initial_size)
        
        with self._lock:
            # 查找合适大小的缓冲区
            for i, buffer in enumerate(self._pool):
                if len(buffer) >= min_size:
                    return self._pool.pop(i)
                    
            # 创建新的缓冲区
            return bytearray(min_size)
            
    def put(self, buffer: bytearray):
        """归还缓冲区"""
        if not isinstance(buffer, bytearray):
            return
            
        with self._lock:
            if len(self._pool) < self.max_size:
                # 清空缓冲区
                buffer[:] = b''
                self._pool.append(buffer)
                # 按大小排序，小的在前面
                self._pool.sort(key=len)

# 全局对象池实例
_request_pool = MessagePool(dict, max_size=100)
_response_pool = MessagePool(dict, max_size=100) 
_buffer_pool = BufferPool(initial_size=1024, max_size=50)

# 统计信息
_message_stats = {
    "total_encoded": 0,
    "total_decoded": 0,
    "total_encode_time": 0.0,
    "total_decode_time": 0.0
}

def get_pool_stats() -> Dict[str, Any]:
    """获取池统计信息"""
    return {
        "request_pool": _request_pool.get_stats(),
        "response_pool": _response_pool.get_stats(),
        "buffer_pool_size": len(_buffer_pool._pool),
        "message_stats": {
            "total_encoded": _message_stats["total_encoded"],
            "total_decoded": _message_stats["total_decoded"],
            "avg_encode_time_ms": (
                _message_stats["total_encode_time"] / max(_message_stats["total_encoded"], 1) * 1000
            ),
            "avg_decode_time_ms": (
                _message_stats["total_decode_time"] / max(_message_stats["total_decoded"], 1) * 1000
            )
        }
    }

async def create_request_batch(requests: List[Any]) -> List[bytes]:
    """批量创建请求"""
    results = []
    for request in requests:
        start = time.perf_counter()
        data = await request.to_bytes()
        _message_stats["total_encode_time"] += time.perf_counter() - start
        _message_stats["total_encoded"] += 1
        results.append(data)
    return results

async def create_response_batch(responses: List[Any]) -> List[bytes]:
    """批量创建响应"""
    results = []
    for response in responses:
        start = time.perf_counter()
        data = await response.to_bytes()
        _message_stats["total_encode_time"] += time.perf_counter() - start
        _message_stats["total_encoded"] += 1
        results.append(data)
    return results