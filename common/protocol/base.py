"""
Protocol基础类实现
Protocol Base Classes Implementation

作者: lx
日期: 2025-06-18
描述: 实现BaseRequest和BaseResponse的Python基类，提供消息序列化、反序列化和池化复用机制
"""

import asyncio
import hashlib
import time
from typing import Optional, Type, TypeVar, Generic, Dict, Any, List
from dataclasses import dataclass
from collections import deque
import struct

from common.protocol.base_message_pb2 import Header, BaseRequest as PBBaseRequest, BaseResponse as PBBaseResponse

# 类型变量定义
T = TypeVar('T')

# 消息池配置
MESSAGE_POOL_SIZE = 1000  # 消息池最大大小
BUFFER_POOL_SIZE = 100    # 缓冲区池大小


class MessagePool(Generic[T]):
    """
    消息对象池，用于复用消息对象以减少GC压力
    Message object pool for reusing message objects to reduce GC pressure
    """
    
    def __init__(self, message_class: Type[T], max_size: int = MESSAGE_POOL_SIZE):
        """
        初始化消息池
        
        Args:
            message_class: 消息类型
            max_size: 池最大容量
        """
        self._message_class = message_class
        self._max_size = max_size
        self._pool: deque = deque()
        self._created_count = 0
        self._reused_count = 0
    
    def get(self) -> T:
        """
        从池中获取消息对象
        Get message object from pool
        """
        if self._pool:
            self._reused_count += 1
            return self._pool.popleft()
        else:
            self._created_count += 1
            return self._message_class()
    
    def put(self, obj: T) -> None:
        """
        归还消息对象到池中
        Return message object to pool
        """
        if len(self._pool) < self._max_size:
            # 清理对象状态
            if hasattr(obj, 'clear'):
                obj.clear()
            self._pool.append(obj)
    
    @property
    def stats(self) -> Dict[str, int]:
        """获取池统计信息"""
        return {
            'pool_size': len(self._pool),
            'created_count': self._created_count,
            'reused_count': self._reused_count,
            'reuse_ratio': self._reused_count / max(1, self._created_count + self._reused_count)
        }


class BufferPool:
    """
    缓冲区池，用于复用字节缓冲区
    Buffer pool for reusing byte buffers
    """
    
    def __init__(self, initial_size: int = 1024, max_size: int = BUFFER_POOL_SIZE):
        """
        初始化缓冲区池
        
        Args:
            initial_size: 初始缓冲区大小
            max_size: 池最大容量
        """
        self._initial_size = initial_size
        self._max_size = max_size
        self._pool: deque = deque()
    
    def get(self, min_size: int = 0) -> bytearray:
        """
        获取缓冲区
        
        Args:
            min_size: 最小缓冲区大小
            
        Returns:
            bytearray: 缓冲区对象
        """
        if self._pool:
            buffer = self._pool.popleft()
            if len(buffer) >= min_size:
                return buffer
        
        # 创建新缓冲区
        size = max(self._initial_size, min_size)
        return bytearray(size)
    
    def put(self, buffer: bytearray) -> None:
        """
        归还缓冲区
        
        Args:
            buffer: 要归还的缓冲区
        """
        if len(self._pool) < self._max_size and len(buffer) <= 65536:  # 限制最大缓冲区大小
            # 清空缓冲区内容
            buffer[:] = b'\x00' * len(buffer)
            self._pool.append(buffer)


# 全局池实例
_request_pool = MessagePool(PBBaseRequest)
_response_pool = MessagePool(PBBaseResponse)
_buffer_pool = BufferPool()


@dataclass
class MessageStats:
    """消息统计信息"""
    total_encoded: int = 0
    total_decoded: int = 0
    total_bytes_encoded: int = 0
    total_bytes_decoded: int = 0
    avg_encode_time: float = 0.0
    avg_decode_time: float = 0.0


class BaseMessage:
    """
    消息基类，提供通用的序列化和反序列化功能
    Base message class providing common serialization/deserialization functionality
    """
    
    _stats = MessageStats()
    _sequence_counter = 0
    
    def __init__(self):
        """初始化基础消息"""
        self._pb_message: Optional[PBBaseRequest | PBBaseResponse] = None
        self._cached_data: Optional[bytes] = None
        self._is_dirty = True
    
    @classmethod
    def _generate_sequence(cls) -> int:
        """生成序列号"""
        cls._sequence_counter += 1
        return cls._sequence_counter
    
    @staticmethod
    def _calculate_checksum(data: bytes) -> int:
        """
        计算数据校验和
        
        Args:
            data: 要计算校验和的数据
            
        Returns:
            int: 校验和值
        """
        return struct.unpack('>I', hashlib.md5(data).digest()[:4])[0]
    
    @property
    def pb_message(self):
        """获取Protocol Buffer消息对象"""
        return self._pb_message
    
    def clear(self) -> None:
        """清理消息状态，为池化复用做准备"""
        if self._pb_message:
            self._pb_message.Clear()
        self._cached_data = None
        self._is_dirty = True


class BaseRequest(BaseMessage):
    """
    基础请求消息类
    Base request message class
    """
    
    def __init__(self, player_id: str = "", payload: bytes = b"", msg_id: int = 0):
        """
        初始化请求消息
        
        Args:
            player_id: 玩家ID
            payload: 有效负载数据
            msg_id: 消息ID
        """
        super().__init__()
        self._pb_message = _request_pool.get()
        
        # 设置消息头
        header = self._pb_message.header
        header.msg_id = msg_id
        header.sequence = self._generate_sequence()
        header.length = 0  # 将在序列化时计算
        header.checksum = 0  # 将在序列化时计算
        
        # 设置消息体
        self._pb_message.player_id = player_id
        self._pb_message.timestamp = int(time.time() * 1000)  # 毫秒时间戳
        self._pb_message.payload = payload
        
        self._is_dirty = True
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'BaseRequest':
        """
        从字节数据反序列化创建请求消息
        
        Args:
            data: 序列化的字节数据
            
        Returns:
            BaseRequest: 反序列化的请求消息
            
        Raises:
            ValueError: 数据格式错误或校验和不匹配
        """
        start_time = time.perf_counter()
        
        try:
            request = cls()
            pb_request = request._pb_message
            pb_request.ParseFromString(data)
            
            # 验证校验和
            header = pb_request.header
            stored_checksum = header.checksum
            
            # 临时设置校验和为0来计算期望的校验和
            header.checksum = 0
            payload_data_for_checksum = pb_request.SerializeToString()
            expected_checksum = cls._calculate_checksum(payload_data_for_checksum)
            
            # 恢复原校验和
            header.checksum = stored_checksum
            
            if stored_checksum != expected_checksum:
                raise ValueError(f"Checksum mismatch: expected {expected_checksum}, got {stored_checksum}")
            
            request._cached_data = data
            request._is_dirty = False
            
            # 更新统计信息
            decode_time = time.perf_counter() - start_time
            cls._stats.total_decoded += 1
            cls._stats.total_bytes_decoded += len(data)
            cls._stats.avg_decode_time = (
                (cls._stats.avg_decode_time * (cls._stats.total_decoded - 1) + decode_time) 
                / cls._stats.total_decoded
            )
            
            return request
            
        except Exception as e:
            # 归还对象到池中
            if 'request' in locals():
                _request_pool.put(request._pb_message)
            raise ValueError(f"Failed to deserialize request: {e}")
    
    async def to_bytes(self) -> bytes:
        """
        异步序列化为字节数据
        
        Returns:
            bytes: 序列化后的字节数据
        """
        if not self._is_dirty and self._cached_data:
            return self._cached_data
        
        start_time = time.perf_counter()
        
        # 先设置校验和和长度为0，序列化得到基础数据
        header = self._pb_message.header
        header.checksum = 0
        header.length = 0
        temp_data = self._pb_message.SerializeToString()
        
        # 设置长度后重新序列化计算校验和
        header.length = len(temp_data)
        temp_data = self._pb_message.SerializeToString()
        header.checksum = self._calculate_checksum(temp_data)
        
        # 最终序列化
        self._cached_data = self._pb_message.SerializeToString()
        self._is_dirty = False
        
        # 更新统计信息
        encode_time = time.perf_counter() - start_time
        self._stats.total_encoded += 1
        self._stats.total_bytes_encoded += len(self._cached_data)
        self._stats.avg_encode_time = (
            (self._stats.avg_encode_time * (self._stats.total_encoded - 1) + encode_time) 
            / self._stats.total_encoded
        )
        
        return self._cached_data
    
    @property
    def player_id(self) -> str:
        """获取玩家ID"""
        return self._pb_message.player_id
    
    @player_id.setter
    def player_id(self, value: str) -> None:
        """设置玩家ID"""
        self._pb_message.player_id = value
        self._is_dirty = True
    
    @property
    def payload(self) -> bytes:
        """获取有效负载"""
        return self._pb_message.payload
    
    @payload.setter
    def payload(self, value: bytes) -> None:
        """设置有效负载"""
        self._pb_message.payload = value
        self._is_dirty = True
    
    @property
    def msg_id(self) -> int:
        """获取消息ID"""
        return self._pb_message.header.msg_id
    
    @property
    def sequence(self) -> int:
        """获取序列号"""
        return self._pb_message.header.sequence
    
    @property
    def timestamp(self) -> int:
        """获取时间戳"""
        return self._pb_message.timestamp
    
    def __del__(self):
        """析构函数，归还对象到池中"""
        if hasattr(self, '_pb_message') and self._pb_message:
            _request_pool.put(self._pb_message)


class BaseResponse(BaseMessage):
    """
    基础响应消息类
    Base response message class
    """
    
    def __init__(self, code: int = 0, message: str = "", payload: bytes = b"", 
                 request_sequence: int = 0, msg_id: int = 0):
        """
        初始化响应消息
        
        Args:
            code: 响应码 (0表示成功)
            message: 响应消息
            payload: 有效负载数据
            request_sequence: 对应请求的序列号
            msg_id: 消息ID
        """
        super().__init__()
        self._pb_message = _response_pool.get()
        
        # 设置消息头
        header = self._pb_message.header
        header.msg_id = msg_id
        header.sequence = request_sequence  # 使用请求的序列号
        header.length = 0  # 将在序列化时计算
        header.checksum = 0  # 将在序列化时计算
        
        # 设置消息体
        self._pb_message.code = code
        self._pb_message.message = message
        self._pb_message.payload = payload
        
        self._is_dirty = True
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'BaseResponse':
        """
        从字节数据反序列化创建响应消息
        
        Args:
            data: 序列化的字节数据
            
        Returns:
            BaseResponse: 反序列化的响应消息
            
        Raises:
            ValueError: 数据格式错误或校验和不匹配
        """
        start_time = time.perf_counter()
        
        try:
            response = cls()
            pb_response = response._pb_message
            pb_response.ParseFromString(data)
            
            # 验证校验和
            header = pb_response.header
            stored_checksum = header.checksum
            
            # 临时设置校验和为0来计算期望的校验和
            header.checksum = 0
            payload_data_for_checksum = pb_response.SerializeToString()
            expected_checksum = cls._calculate_checksum(payload_data_for_checksum)
            
            # 恢复原校验和
            header.checksum = stored_checksum
            
            if stored_checksum != expected_checksum:
                raise ValueError(f"Checksum mismatch: expected {expected_checksum}, got {stored_checksum}")
            
            response._cached_data = data
            response._is_dirty = False
            
            # 更新统计信息
            decode_time = time.perf_counter() - start_time
            cls._stats.total_decoded += 1
            cls._stats.total_bytes_decoded += len(data)
            cls._stats.avg_decode_time = (
                (cls._stats.avg_decode_time * (cls._stats.total_decoded - 1) + decode_time) 
                / cls._stats.total_decoded
            )
            
            return response
            
        except Exception as e:
            # 归还对象到池中
            if 'response' in locals():
                _response_pool.put(response._pb_message)
            raise ValueError(f"Failed to deserialize response: {e}")
    
    async def to_bytes(self) -> bytes:
        """
        异步序列化为字节数据
        
        Returns:
            bytes: 序列化后的字节数据
        """
        if not self._is_dirty and self._cached_data:
            return self._cached_data
        
        start_time = time.perf_counter()
        
        # 先设置校验和和长度为0，序列化得到基础数据
        header = self._pb_message.header
        header.checksum = 0
        header.length = 0
        temp_data = self._pb_message.SerializeToString()
        
        # 设置长度后重新序列化计算校验和
        header.length = len(temp_data)
        temp_data = self._pb_message.SerializeToString()
        header.checksum = self._calculate_checksum(temp_data)
        
        # 最终序列化
        self._cached_data = self._pb_message.SerializeToString()
        self._is_dirty = False
        
        # 更新统计信息
        encode_time = time.perf_counter() - start_time
        self._stats.total_encoded += 1
        self._stats.total_bytes_encoded += len(self._cached_data)
        self._stats.avg_encode_time = (
            (self._stats.avg_encode_time * (self._stats.total_encoded - 1) + encode_time) 
            / self._stats.total_encoded
        )
        
        return self._cached_data
    
    @property
    def code(self) -> int:
        """获取响应码"""
        return self._pb_message.code
    
    @code.setter
    def code(self, value: int) -> None:
        """设置响应码"""
        self._pb_message.code = value
        self._is_dirty = True
    
    @property
    def message(self) -> str:
        """获取响应消息"""
        return self._pb_message.message
    
    @message.setter
    def message(self, value: str) -> None:
        """设置响应消息"""
        self._pb_message.message = value
        self._is_dirty = True
    
    @property
    def payload(self) -> bytes:
        """获取有效负载"""
        return self._pb_message.payload
    
    @payload.setter
    def payload(self, value: bytes) -> None:
        """设置有效负载"""
        self._pb_message.payload = value
        self._is_dirty = True
    
    @property
    def msg_id(self) -> int:
        """获取消息ID"""
        return self._pb_message.header.msg_id
    
    @property
    def sequence(self) -> int:
        """获取序列号"""
        return self._pb_message.header.sequence
    
    @classmethod
    def success(cls, payload: bytes = b"", request_sequence: int = 0, msg_id: int = 0) -> 'BaseResponse':
        """
        创建成功响应
        
        Args:
            payload: 响应数据
            request_sequence: 对应请求的序列号
            msg_id: 消息ID
            
        Returns:
            BaseResponse: 成功响应消息
        """
        return cls(code=0, message="Success", payload=payload, 
                  request_sequence=request_sequence, msg_id=msg_id)
    
    @classmethod
    def error(cls, code: int, message: str, request_sequence: int = 0, msg_id: int = 0) -> 'BaseResponse':
        """
        创建错误响应
        
        Args:
            code: 错误码
            message: 错误消息
            request_sequence: 对应请求的序列号
            msg_id: 消息ID
            
        Returns:
            BaseResponse: 错误响应消息
        """
        return cls(code=code, message=message, request_sequence=request_sequence, msg_id=msg_id)
    
    def __del__(self):
        """析构函数，归还对象到池中"""
        if hasattr(self, '_pb_message') and self._pb_message:
            _response_pool.put(self._pb_message)


def get_pool_stats() -> Dict[str, Any]:
    """
    获取所有池的统计信息
    Get statistics for all pools
    
    Returns:
        Dict[str, Any]: 包含各个池统计信息的字典
    """
    return {
        'request_pool': _request_pool.stats,
        'response_pool': _response_pool.stats,
        'buffer_pool_size': len(_buffer_pool._pool),
        'message_stats': {
            'total_encoded': BaseMessage._stats.total_encoded,
            'total_decoded': BaseMessage._stats.total_decoded,
            'total_bytes_encoded': BaseMessage._stats.total_bytes_encoded,
            'total_bytes_decoded': BaseMessage._stats.total_bytes_decoded,
            'avg_encode_time_ms': BaseMessage._stats.avg_encode_time * 1000,
            'avg_decode_time_ms': BaseMessage._stats.avg_decode_time * 1000,
        }
    }


async def create_request_batch(requests: List[BaseRequest]) -> List[bytes]:
    """
    批量创建请求消息的字节数据
    Create byte data for a batch of request messages
    
    Args:
        requests: 请求消息列表
        
    Returns:
        List[bytes]: 序列化后的字节数据列表
    """
    tasks = [request.to_bytes() for request in requests]
    return await asyncio.gather(*tasks)


async def create_response_batch(responses: List[BaseResponse]) -> List[bytes]:
    """
    批量创建响应消息的字节数据
    Create byte data for a batch of response messages
    
    Args:
        responses: 响应消息列表
        
    Returns:
        List[bytes]: 序列化后的字节数据列表
    """
    tasks = [response.to_bytes() for response in responses]
    return await asyncio.gather(*tasks)