"""
消息解码器
负责将字节流解码为消息对象
作者: lx
日期: 2025-06-18
"""
import struct
from typing import Optional, List, Any
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
        body = bytes(self._buffer[body_start:body_end])  # Convert to bytes
        
        # 更新位置
        self._buffer_pos += total_len
        
        # 解密
        if flags & 0x02:
            if hasattr(self, '_cipher'):
                # Use the specific cipher instance
                body = self._cipher.decrypt(body)
            else:
                # Use default cipher
                try:
                    from ..crypto.aes_cipher import AESCipher
                    cipher = AESCipher()
                    body = cipher.decrypt(body)
                except ImportError:
                    pass  # 没有加密模块则跳过解密
            
        # 解压缩
        if flags & 0x01:
            try:
                import lz4.frame
                body = lz4.frame.decompress(body)
            except ImportError:
                pass  # 没有lz4库则跳过解压缩
            
        # 查找消息类
        msg_class = MESSAGE_REGISTRY.get(msg_type)
        if not msg_class:
            # 创建一个通用的消息对象
            from ..core.base_request import BaseRequest
            message = BaseRequest()
            message.msg_id = msg_type
        else:
            message = msg_class()
            
        # 反序列化
        if hasattr(message, "ParseFromString"):
            # Protobuf消息
            message.ParseFromString(body)
        else:
            # msgpack消息
            try:
                data = msgpack.unpackb(body, raw=False)
                if hasattr(message, 'from_dict'):
                    message.from_dict(data)
                else:
                    for key, value in data.items():
                        if hasattr(message, key):
                            setattr(message, key, value)
            except Exception:
                # 如果解码失败，至少设置基本信息
                message.msg_id = msg_type
                message.payload = body
            
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