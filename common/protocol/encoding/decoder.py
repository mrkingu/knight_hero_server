"""
消息解码器
负责将字节流解码为消息对象
作者: lx
日期: 2025-06-18
"""
import struct
from typing import Optional, List, Tuple, Any
import msgpack
from ..core.decorators import MESSAGE_REGISTRY

class MessageDecoder:
    """消息解码器"""
    
    def __init__(self, buffer_size: int = 65536):
        self._buffer = bytearray(buffer_size)
        self._buffer_pos = 0
        self._buffer_end = 0
        
    def feed(self, data: bytes):
        """添加数据到缓冲区"""
        data_len = len(data)
        
        # 确保缓冲区足够大
        if self._buffer_end + data_len > len(self._buffer):
            # 压缩缓冲区
            if self._buffer_pos > 0:
                self._buffer[:self._buffer_end - self._buffer_pos] = self._buffer[self._buffer_pos:self._buffer_end]
                self._buffer_end -= self._buffer_pos
                self._buffer_pos = 0
                
            # 扩展缓冲区
            if self._buffer_end + data_len > len(self._buffer):
                new_size = max(len(self._buffer) * 2, self._buffer_end + data_len)
                new_buffer = bytearray(new_size)
                new_buffer[:self._buffer_end] = self._buffer[:self._buffer_end]
                self._buffer = new_buffer
                
        # 复制数据
        self._buffer[self._buffer_end:self._buffer_end + data_len] = data
        self._buffer_end += data_len
        
    def decode(self) -> Optional[Any]:
        """解码一个消息"""
        # 检查是否有足够的头部数据
        if self._buffer_end - self._buffer_pos < 7:
            return None
            
        # 解析头部
        msg_len, msg_type, flags = struct.unpack_from(
            "!IHB", self._buffer, self._buffer_pos
        )
        
        # 检查是否有完整的消息
        total_len = 7 + msg_len
        if self._buffer_end - self._buffer_pos < total_len:
            return None
            
        # 提取消息体
        body_start = self._buffer_pos + 7
        body_end = body_start + msg_len
        body = bytes(self._buffer[body_start:body_end])
        
        # 更新位置
        self._buffer_pos += total_len
        
        # 解密
        if flags & 0x02:
            if hasattr(self, '_cipher'):
                body = self._cipher.decrypt(body)
            else:
                from ..crypto.aes_cipher import AESCipher
                cipher = AESCipher()
                body = cipher.decrypt(body)
            
        # 解压缩
        if flags & 0x01:
            import lz4.frame
            body = lz4.frame.decompress(body)
            
        # 查找消息类
        msg_class = MESSAGE_REGISTRY.get(msg_type)
        if not msg_class:
            # If not registered, create a generic BaseRequest/BaseResponse
            from ..core.base_request import BaseRequest
            from ..core.base_response import BaseResponse
            from ..core.message_type import MessageType
            
            # Choose appropriate base class based on message type
            if MessageType.is_response(msg_type):
                message = BaseResponse()
            else:
                message = BaseRequest()
            message.MESSAGE_TYPE = msg_type
        else:
            message = msg_class()
            
        # 反序列化
        if hasattr(message, "ParseFromString"):
            # Protobuf消息
            message.ParseFromString(body)
        else:
            # msgpack消息
            data = msgpack.unpackb(body, raw=False)
            message.from_dict(data)
            
        return message
        
    def decode_all(self) -> List[Any]:
        """解码所有可用的消息"""
        messages = []
        while True:
            msg = self.decode()
            if msg is None:
                break
            messages.append(msg)
        return messages