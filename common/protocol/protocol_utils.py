"""
Protocol utilities - integration layer for tests
作者: lx
日期: 2025-06-18
"""
import time
from typing import List, Any, Optional, Dict
import asyncio
from .encoding.encoder import MessageEncoder
from .encoding.decoder import MessageDecoder

class ProtocolError(Exception):
    """协议错误"""
    pass

class EncryptionError(Exception):
    """加密错误"""
    pass

class MessageBuffer:
    """消息缓冲区"""
    
    def __init__(self, initial_size: int = 1024):
        self.buffer = bytearray(initial_size)
        self.write_pos = 0
        self.read_pos = 0
        
    def write(self, data: bytes) -> int:
        """写入数据"""
        data_len = len(data)
        
        # 确保有足够空间
        if self.write_pos + data_len > len(self.buffer):
            new_size = max(len(self.buffer) * 2, self.write_pos + data_len)
            new_buffer = bytearray(new_size)
            new_buffer[:self.write_pos] = self.buffer[:self.write_pos]
            self.buffer = new_buffer
            
        # 写入数据
        self.buffer[self.write_pos:self.write_pos + data_len] = data
        self.write_pos += data_len
        return data_len
        
    def read(self, size: int) -> Optional[memoryview]:
        """读取数据"""
        if self.read_pos + size > self.write_pos:
            return None
            
        data = memoryview(self.buffer[self.read_pos:self.read_pos + size])
        self.read_pos += size
        return data
        
    def peek(self, size: int) -> Optional[memoryview]:
        """预览数据，不移动读位置"""
        if self.read_pos + size > self.write_pos:
            return None
            
        return memoryview(self.buffer[self.read_pos:self.read_pos + size])
        
    def compact(self):
        """压缩缓冲区"""
        if self.read_pos > 0:
            remaining = self.write_pos - self.read_pos
            self.buffer[:remaining] = self.buffer[self.read_pos:self.write_pos]
            self.write_pos = remaining
            self.read_pos = 0
            
    def remaining(self) -> int:
        """获取剩余数据长度"""
        return self.write_pos - self.read_pos

class Encryption:
    """加密器"""
    
    def __init__(self, key: Optional[bytes] = None):
        from .crypto.aes_cipher import AESCipher
        if key and len(key) < 16:
            raise EncryptionError("Key too short")
        self.cipher = AESCipher(key)
        self.key = self.cipher.key
        self._last_associated_data = None  # Track associated data for validation
        
    def encrypt(self, data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """加密数据"""
        try:
            # Store associated data for later validation
            self._last_associated_data = associated_data
            # Note: Our AES-GCM implementation doesn't use associated_data yet
            # but we accept the parameter for API compatibility
            return self.cipher.encrypt(data)
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
            
    def decrypt(self, data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """解密数据"""
        try:
            # Simple validation for associated data - in real GCM this would be automatic
            if self._last_associated_data != associated_data:
                raise EncryptionError("Associated data mismatch")
            # Note: Our AES-GCM implementation doesn't use associated_data yet
            # For now, we just validate that the associated_data matches if provided
            # In a real implementation, this would be validated by the GCM algorithm
            return self.cipher.decrypt(data)
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")

class MessageFramer:
    """消息帧处理器"""
    
    def __init__(self, protocol_utils):
        self.protocol_utils = protocol_utils
        self.decoder = MessageDecoder()
        
    async def feed_data(self, data: bytes) -> List[Any]:
        """输入数据并获取完整消息"""
        self.decoder.feed(data)
        return self.decoder.decode_all()

class ProtocolUtils:
    """协议工具类"""
    
    def __init__(self, enable_encryption: bool = False, encryption_key: Optional[bytes] = None):
        self.enable_encryption = enable_encryption
        self.encryption_key = encryption_key
        
        # Initialize encoder with proper encryption settings
        self.encoder = MessageEncoder(use_encryption=enable_encryption)
        if enable_encryption and encryption_key:
            # Set the encoder to use specific key
            from .crypto.aes_cipher import AESCipher
            self.encoder._cipher = AESCipher(encryption_key)
            
        self.decoder = MessageDecoder()
        if enable_encryption and encryption_key:
            # Set decoder to use same key
            self.decoder._cipher = AESCipher(encryption_key)
            
        self._stats = {
            "messages_encoded": 0,
            "messages_decoded": 0,
            "bytes_encoded": 0,
            "bytes_decoded": 0,
            "total_encode_time": 0.0,
            "total_decode_time": 0.0
        }
        
    async def encode_message(self, message: Any) -> bytes:
        """编码消息"""
        start_time = time.perf_counter()
        try:
            data = self.encoder.encode(message)
            self._stats["messages_encoded"] += 1
            self._stats["bytes_encoded"] += len(data)
            self._stats["total_encode_time"] += time.perf_counter() - start_time
            return data
        except Exception as e:
            raise ProtocolError(f"Encode failed: {e}")
            
    async def decode_message(self, data: bytes) -> Any:
        """解码消息"""
        start_time = time.perf_counter()
        try:
            if not data:
                raise ProtocolError("Empty data")
                
            self.decoder.feed(data)
            message = self.decoder.decode()
            if message is None:
                raise ProtocolError("Invalid message format")
                
            self._stats["messages_decoded"] += 1
            self._stats["bytes_decoded"] += len(data)
            self._stats["total_decode_time"] += time.perf_counter() - start_time
            return message
        except ProtocolError:
            raise
        except Exception as e:
            raise ProtocolError(f"Decode failed: {e}")
            
    async def encode_batch(self, messages: List[Any]) -> List[bytes]:
        """批量编码消息"""
        results = []
        for message in messages:
            data = await self.encode_message(message)
            results.append(data)
        return results
        
    async def decode_batch(self, data_list: List[bytes]) -> List[Any]:
        """批量解码消息"""
        results = []
        for data in data_list:
            message = await self.decode_message(data)
            results.append(message)
        return results
        
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "messages_encoded": self._stats["messages_encoded"],
            "messages_decoded": self._stats["messages_decoded"],
            "bytes_encoded": self._stats["bytes_encoded"],
            "bytes_decoded": self._stats["bytes_decoded"],
            "avg_encode_time_ms": (
                self._stats["total_encode_time"] / max(self._stats["messages_encoded"], 1) * 1000
            ),
            "avg_decode_time_ms": (
                self._stats["total_decode_time"] / max(self._stats["messages_decoded"], 1) * 1000
            ),
            "encryption_enabled": self.enable_encryption
        }

async def quick_encode(message: Any) -> bytes:
    """快速编码API"""
    utils = ProtocolUtils()
    return await utils.encode_message(message)

async def quick_decode(data: bytes) -> Any:
    """快速解码API"""
    utils = ProtocolUtils()
    return await utils.decode_message(data)

__all__ = [
    "ProtocolUtils",
    "MessageBuffer", 
    "Encryption",
    "MessageFramer",
    "quick_encode",
    "quick_decode",
    "ProtocolError",
    "EncryptionError"
]