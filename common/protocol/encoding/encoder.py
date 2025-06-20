"""
消息编码器
负责将消息对象编码为字节流
作者: lx
日期: 2025-06-18
"""
import struct
from typing import Optional
import msgpack
from google.protobuf import message as protobuf_message

class MessageEncoder:
    """消息编码器"""
    
    def __init__(self, use_compression: bool = False, use_encryption: bool = False):
        self.use_compression = use_compression
        self.use_encryption = use_encryption
        self._buffer = bytearray(65536)  # 64KB预分配缓冲区
        
    def encode(self, message) -> bytes:
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
        msg_type = message.MESSAGE_TYPE
        
        # 序列化消息体
        if isinstance(message, protobuf_message.Message):
            # Protobuf消息
            body = message.SerializeToString()
        else:
            # 使用msgpack序列化
            body = msgpack.packb(message.to_dict())
            
        # 压缩
        flags = 0
        if self.use_compression and len(body) > 128:  # 只压缩大于128字节的消息
            import lz4.frame
            body = lz4.frame.compress(body)
            flags |= 0x01
            
        # 加密
        if self.use_encryption:
            if hasattr(self, '_cipher'):
                body = self._cipher.encrypt(body)
            else:
                from ..crypto.aes_cipher import AESCipher
                cipher = AESCipher()
                body = cipher.encrypt(body)
            flags |= 0x02
            
        # 构建消息
        header_size = 7  # 4 + 2 + 1
        total_size = header_size + len(body)
        
        # 确保缓冲区足够大
        if total_size > len(self._buffer):
            self._buffer = bytearray(total_size * 2)
        
        # 写入头部
        struct.pack_into("!IHB", self._buffer, 0, len(body), msg_type, flags)
        
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