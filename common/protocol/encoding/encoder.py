"""
消息编码器
负责将消息对象编码为字节流
作者: lx
日期: 2025-06-18
"""
import struct
from typing import Optional, Any
import msgpack

class MessageEncoder:
    """消息编码器"""
    
    def __init__(self, use_compression: bool = False, use_encryption: bool = False):
        self.use_compression = use_compression
        self.use_encryption = use_encryption
        self._buffer = bytearray(65536)  # 64KB预分配缓冲区
        
    def encode(self, message: Any) -> bytes:
        """
        编码消息
        
        消息格式:
        [4字节长度][2字节消息类型][1字节标志位][消息体]
        
        标志位:
        bit 0: 是否压缩
        bit 1: 是否加密
        bit 2-7: 保留
        """
        # 获取消息类型
        msg_type = getattr(message, 'MESSAGE_TYPE', 0)
        if hasattr(message, 'msg_id') and message.msg_id:
            msg_type = message.msg_id
        
        # 序列化消息体
        if hasattr(message, 'SerializeToString'):
            # Protobuf消息
            body = message.SerializeToString()
        else:
            # 使用msgpack序列化
            if hasattr(message, 'to_dict'):
                body = msgpack.packb(message.to_dict())
            else:
                body = msgpack.packb(message.__dict__)
            
        # 压缩
        flags = 0
        if self.use_compression and len(body) > 128:  # 只压缩大于128字节的消息
            try:
                import lz4.frame
                body = lz4.frame.compress(body)
                flags |= 0x01
            except ImportError:
                pass  # 没有lz4库则跳过压缩
            
        # 加密
        if self.use_encryption:
            if hasattr(self, '_cipher'):
                # Use the specific cipher instance
                body = self._cipher.encrypt(body)
                flags |= 0x02
            else:
                # Use default cipher
                try:
                    from ..crypto.aes_cipher import AESCipher
                    cipher = AESCipher()
                    body = cipher.encrypt(body)
                    flags |= 0x02
                except ImportError:
                    pass  # 没有加密模块则跳过加密
            
        # 构建消息
        header_size = 7  # 4 + 2 + 1
        total_size = header_size + len(body)
        
        # 确保缓冲区足够大
        if total_size > len(self._buffer):
            self._buffer = bytearray(total_size * 2)
        
        # 写入头部
        struct.pack_into("!Ihb", self._buffer, 0, len(body), msg_type, flags)
        
        # 写入消息体
        self._buffer[header_size:header_size + len(body)] = body
        
        # 返回结果
        return bytes(self._buffer[:total_size])
        
    def encode_batch(self, messages: list) -> bytes:
        """批量编码消息"""
        results = []
        for msg in messages:
            results.append(self.encode(msg))
        return b''.join(results)