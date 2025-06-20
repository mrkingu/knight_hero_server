"""
Protocol工具类实现
Protocol Utilities Implementation

作者: lx
日期: 2025-06-18
描述: 实现消息编解码工具类，处理消息缓冲区，消息加密解密，零拷贝传输优化
"""

import asyncio
import struct
import time
from typing import Optional, Union, List, Tuple, Dict, Any
from collections import deque
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import os

from common.protocol.base import BaseRequest, BaseResponse, _buffer_pool


# 日志配置
logger = logging.getLogger(__name__)

# 协议常量
PROTOCOL_VERSION = 1
MAGIC_HEADER = b'\x4B\x48\x47\x53'  # "KHGS" - Knight Hero Game Server
HEADER_SIZE = 16  # 魔术头(4) + 版本(4) + 长度(4) + 标志(4)
MAX_MESSAGE_SIZE = 16 * 1024 * 1024  # 16MB 最大消息大小
ENCRYPTION_KEY_SIZE = 16  # AES-128 密钥大小


class ProtocolError(Exception):
    """协议相关错误"""
    pass


class EncryptionError(ProtocolError):
    """加密相关错误"""
    pass


class MessageBuffer:
    """
    消息缓冲区，支持零拷贝操作
    Message buffer supporting zero-copy operations
    """
    
    def __init__(self, initial_size: int = 8192):
        """
        初始化消息缓冲区
        
        Args:
            initial_size: 初始缓冲区大小
        """
        self._buffer = _buffer_pool.get(initial_size)
        self._position = 0
        self._limit = 0
        self._capacity = len(self._buffer)
    
    def write(self, data: Union[bytes, bytearray, memoryview]) -> int:
        """
        写入数据到缓冲区
        
        Args:
            data: 要写入的数据
            
        Returns:
            int: 实际写入的字节数
            
        Raises:
            ProtocolError: 缓冲区空间不足
        """
        data_len = len(data)
        if self._position + data_len > self._capacity:
            # 尝试扩展缓冲区
            self._expand(self._position + data_len)
        
        # 使用memoryview进行零拷贝写入
        dest_view = memoryview(self._buffer)[self._position:self._position + data_len]
        if isinstance(data, (bytes, bytearray)):
            dest_view[:] = data
        else:  # memoryview
            dest_view[:] = data[:]
        
        self._position += data_len
        self._limit = max(self._limit, self._position)
        return data_len
    
    def read(self, length: int) -> Optional[memoryview]:
        """
        从缓冲区读取数据
        
        Args:
            length: 要读取的字节数
            
        Returns:
            Optional[memoryview]: 读取的数据视图，如果数据不足返回None
        """
        if self._position + length > self._limit:
            return None
        
        data_view = memoryview(self._buffer)[self._position:self._position + length]
        self._position += length
        return data_view
    
    def peek(self, length: int) -> Optional[memoryview]:
        """
        预览数据但不移动位置
        
        Args:
            length: 要预览的字节数
            
        Returns:
            Optional[memoryview]: 预览的数据视图
        """
        if self._position + length > self._limit:
            return None
        
        return memoryview(self._buffer)[self._position:self._position + length]
    
    def remaining(self) -> int:
        """获取剩余可读字节数"""
        return self._limit - self._position
    
    def clear(self) -> None:
        """清空缓冲区"""
        self._position = 0
        self._limit = 0
    
    def compact(self) -> None:
        """压缩缓冲区，移除已读数据"""
        if self._position > 0:
            remaining_data = self._limit - self._position
            if remaining_data > 0:
                # 移动剩余数据到缓冲区开始位置
                self._buffer[:remaining_data] = self._buffer[self._position:self._limit]
            self._limit = remaining_data
            self._position = 0
    
    def _expand(self, min_capacity: int) -> None:
        """
        扩展缓冲区容量
        
        Args:
            min_capacity: 最小所需容量
        """
        new_capacity = max(self._capacity * 2, min_capacity)
        new_buffer = _buffer_pool.get(new_capacity)
        
        # 复制现有数据
        if self._limit > 0:
            new_buffer[:self._limit] = self._buffer[:self._limit]
        
        # 归还旧缓冲区
        _buffer_pool.put(self._buffer)
        
        self._buffer = new_buffer
        self._capacity = len(new_buffer)
    
    def to_bytes(self) -> bytes:
        """将缓冲区内容转换为字节"""
        return bytes(self._buffer[:self._limit])
    
    def __len__(self) -> int:
        """获取缓冲区数据长度"""
        return self._limit
    
    def __del__(self):
        """归还缓冲区到池中"""
        if hasattr(self, '_buffer'):
            _buffer_pool.put(self._buffer)


class Encryption:
    """
    消息加密工具，支持AES-128-GCM加密
    Message encryption utility supporting AES-128-GCM
    """
    
    def __init__(self, key: Optional[bytes] = None):
        """
        初始化加密工具
        
        Args:
            key: 加密密钥，如果为None则生成随机密钥
        """
        if key is None:
            key = os.urandom(ENCRYPTION_KEY_SIZE)
        elif len(key) != ENCRYPTION_KEY_SIZE:
            raise EncryptionError(f"Invalid key size: expected {ENCRYPTION_KEY_SIZE}, got {len(key)}")
        
        self._key = key
        self._cipher = AESGCM(key)
    
    @property
    def key(self) -> bytes:
        """获取加密密钥"""
        return self._key
    
    def encrypt(self, data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        加密数据
        
        Args:
            data: 要加密的数据
            associated_data: 关联数据（用于认证但不加密）
            
        Returns:
            bytes: nonce(12字节) + 加密后的数据 + tag(16字节)
            
        Raises:
            EncryptionError: 加密失败
        """
        try:
            nonce = os.urandom(12)  # GCM推荐96位nonce
            ciphertext = self._cipher.encrypt(nonce, data, associated_data)
            return nonce + ciphertext
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: bytes, associated_data: Optional[bytes] = None) -> bytes:
        """
        解密数据
        
        Args:
            encrypted_data: 加密的数据（包含nonce）
            associated_data: 关联数据
            
        Returns:
            bytes: 解密后的原始数据
            
        Raises:
            EncryptionError: 解密失败或数据被篡改
        """
        try:
            if len(encrypted_data) < 12:
                raise EncryptionError("Invalid encrypted data: too short")
            
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            
            return self._cipher.decrypt(nonce, ciphertext, associated_data)
        except InvalidTag:
            raise EncryptionError("Decryption failed: data integrity check failed")
        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")


class ProtocolUtils:
    """
    协议工具类，处理消息的编解码、加密解密等
    Protocol utility class handling message encoding/decoding, encryption/decryption
    """
    
    def __init__(self, enable_encryption: bool = False, encryption_key: Optional[bytes] = None):
        """
        初始化协议工具类
        
        Args:
            enable_encryption: 是否启用加密
            encryption_key: 加密密钥
        """
        self._enable_encryption = enable_encryption
        self._encryption = Encryption(encryption_key) if enable_encryption else None
        
        # 消息缓冲池
        self._buffer_queue: deque = deque(maxlen=100)
        
        # 性能统计
        self._stats = {
            'messages_encoded': 0,
            'messages_decoded': 0,
            'bytes_encoded': 0,
            'bytes_decoded': 0,
            'total_encode_time': 0.0,
            'total_decode_time': 0.0,
            'encryption_enabled': enable_encryption
        }
        
        logger.info(f"ProtocolUtils initialized with encryption={'enabled' if enable_encryption else 'disabled'}")
    
    async def encode_message(self, msg: Union[BaseRequest, BaseResponse]) -> bytes:
        """
        编码消息为字节流
        Encode message to byte stream
        
        Args:
            msg: 要编码的消息对象
            
        Returns:
            bytes: 编码后的字节流
            
        Raises:
            ProtocolError: 编码失败
        """
        start_time = time.perf_counter()
        
        try:
            # 序列化消息
            payload_data = await msg.to_bytes()
            
            # 加密负载（如果启用）
            if self._enable_encryption and self._encryption:
                payload_data = self._encryption.encrypt(payload_data)
            
            # 构造协议头
            flags = 0x01 if self._enable_encryption else 0x00
            header = struct.pack('>4sIII', 
                               MAGIC_HEADER,           # 魔术头
                               PROTOCOL_VERSION,       # 协议版本
                               len(payload_data),      # 负载长度
                               flags)                  # 标志位
            
            # 组合最终数据
            final_data = header + payload_data
            
            # 更新统计
            encode_time = time.perf_counter() - start_time
            self._stats['messages_encoded'] += 1
            self._stats['bytes_encoded'] += len(final_data)
            self._stats['total_encode_time'] += encode_time
            
            return final_data
            
        except Exception as e:
            logger.error(f"Failed to encode message: {e}")
            raise ProtocolError(f"Message encoding failed: {e}")
    
    async def decode_message(self, data: Union[bytes, memoryview]) -> Union[BaseRequest, BaseResponse]:
        """
        解码字节流为消息对象
        Decode byte stream to message object
        
        Args:
            data: 要解码的字节数据
            
        Returns:
            Union[BaseRequest, BaseResponse]: 解码后的消息对象
            
        Raises:
            ProtocolError: 解码失败
        """
        start_time = time.perf_counter()
        
        try:
            # 检查数据长度
            if len(data) < HEADER_SIZE:
                raise ProtocolError(f"Invalid data: too short (got {len(data)}, expected at least {HEADER_SIZE})")
            
            # 解析协议头
            if isinstance(data, memoryview):
                header_data = bytes(data[:HEADER_SIZE])
            else:
                header_data = data[:HEADER_SIZE]
            
            magic, version, payload_length, flags = struct.unpack('>4sIII', header_data)
            
            # 验证魔术头
            if magic != MAGIC_HEADER:
                raise ProtocolError(f"Invalid magic header: {magic}")
            
            # 验证协议版本
            if version != PROTOCOL_VERSION:
                raise ProtocolError(f"Unsupported protocol version: {version}")
            
            # 验证负载长度
            if payload_length > MAX_MESSAGE_SIZE:
                raise ProtocolError(f"Message too large: {payload_length} > {MAX_MESSAGE_SIZE}")
            
            if len(data) < HEADER_SIZE + payload_length:
                raise ProtocolError(f"Incomplete message: expected {HEADER_SIZE + payload_length}, got {len(data)}")
            
            # 提取负载数据
            if isinstance(data, memoryview):
                payload_data = bytes(data[HEADER_SIZE:HEADER_SIZE + payload_length])
            else:
                payload_data = data[HEADER_SIZE:HEADER_SIZE + payload_length]
            
            # 解密负载（如果需要）
            is_encrypted = bool(flags & 0x01)
            if is_encrypted:
                if not self._enable_encryption or not self._encryption:
                    raise ProtocolError("Received encrypted message but encryption is not enabled")
                payload_data = self._encryption.decrypt(payload_data)
            
            # 尝试解析为不同类型的消息
            try:
                # 先尝试解析为请求消息
                message = BaseRequest.from_bytes(payload_data)
            except:
                try:
                    # 再尝试解析为响应消息
                    message = BaseResponse.from_bytes(payload_data)
                except Exception as e:
                    raise ProtocolError(f"Failed to parse message as either request or response: {e}")
            
            # 更新统计
            decode_time = time.perf_counter() - start_time
            self._stats['messages_decoded'] += 1
            self._stats['bytes_decoded'] += len(data)
            self._stats['total_decode_time'] += decode_time
            
            return message
            
        except ProtocolError:
            raise
        except Exception as e:
            logger.error(f"Failed to decode message: {e}")
            raise ProtocolError(f"Message decoding failed: {e}")
    
    async def encode_batch(self, messages: List[Union[BaseRequest, BaseResponse]]) -> List[bytes]:
        """
        批量编码消息
        Batch encode messages
        
        Args:
            messages: 要编码的消息列表
            
        Returns:
            List[bytes]: 编码后的字节流列表
        """
        tasks = [self.encode_message(msg) for msg in messages]
        return await asyncio.gather(*tasks)
    
    async def decode_batch(self, data_list: List[Union[bytes, memoryview]]) -> List[Union[BaseRequest, BaseResponse]]:
        """
        批量解码消息
        Batch decode messages
        
        Args:
            data_list: 要解码的字节数据列表
            
        Returns:
            List[Union[BaseRequest, BaseResponse]]: 解码后的消息列表
        """
        tasks = [self.decode_message(data) for data in data_list]
        return await asyncio.gather(*tasks)
    
    def create_buffer(self, initial_size: int = 8192) -> MessageBuffer:
        """
        创建消息缓冲区
        Create message buffer
        
        Args:
            initial_size: 初始缓冲区大小
            
        Returns:
            MessageBuffer: 消息缓冲区对象
        """
        return MessageBuffer(initial_size)
    
    def parse_frame(self, buffer: MessageBuffer) -> Optional[Tuple[int, memoryview]]:
        """
        从缓冲区解析完整的消息帧
        Parse complete message frame from buffer
        
        Args:
            buffer: 消息缓冲区
            
        Returns:
            Optional[Tuple[int, memoryview]]: (消息长度, 消息数据)，如果没有完整消息返回None
            
        Raises:
            ProtocolError: 协议格式错误
        """
        if buffer.remaining() < HEADER_SIZE:
            return None
        
        # 预览协议头
        header_view = buffer.peek(HEADER_SIZE)
        if header_view is None:
            return None
        
        try:
            header_bytes = bytes(header_view)
            magic, version, payload_length, flags = struct.unpack('>4sIII', header_bytes)
            
            # 验证协议头
            if magic != MAGIC_HEADER:
                raise ProtocolError(f"Invalid magic header: {magic}")
            
            if version != PROTOCOL_VERSION:
                raise ProtocolError(f"Unsupported protocol version: {version}")
            
            if payload_length > MAX_MESSAGE_SIZE:
                raise ProtocolError(f"Message too large: {payload_length}")
            
            # 检查是否有完整消息
            total_length = HEADER_SIZE + payload_length
            if buffer.remaining() < total_length:
                return None
            
            # 读取完整消息
            message_data = buffer.read(total_length)
            return total_length, message_data
            
        except struct.error as e:
            raise ProtocolError(f"Invalid protocol header: {e}")
    
    @property
    def encryption_enabled(self) -> bool:
        """检查是否启用加密"""
        return self._enable_encryption
    
    @property
    def encryption_key(self) -> Optional[bytes]:
        """获取加密密钥"""
        return self._encryption.key if self._encryption else None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息
        Get performance statistics
        
        Returns:
            Dict[str, Any]: 统计信息字典
        """
        stats = self._stats.copy()
        
        # 计算平均性能
        if stats['messages_encoded'] > 0:
            stats['avg_encode_time_ms'] = (stats['total_encode_time'] / stats['messages_encoded']) * 1000
            stats['avg_encode_size'] = stats['bytes_encoded'] / stats['messages_encoded']
        else:
            stats['avg_encode_time_ms'] = 0.0
            stats['avg_encode_size'] = 0.0
        
        if stats['messages_decoded'] > 0:
            stats['avg_decode_time_ms'] = (stats['total_decode_time'] / stats['messages_decoded']) * 1000
            stats['avg_decode_size'] = stats['bytes_decoded'] / stats['messages_decoded']
        else:
            stats['avg_decode_time_ms'] = 0.0
            stats['avg_decode_size'] = 0.0
        
        return stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats.update({
            'messages_encoded': 0,
            'messages_decoded': 0,
            'bytes_encoded': 0,
            'bytes_decoded': 0,
            'total_encode_time': 0.0,
            'total_decode_time': 0.0
        })


class MessageFramer:
    """
    消息帧处理器，用于TCP流数据的消息分帧
    Message framer for handling message framing in TCP streams
    """
    
    def __init__(self, protocol_utils: ProtocolUtils):
        """
        初始化消息帧处理器
        
        Args:
            protocol_utils: 协议工具实例
        """
        self._protocol_utils = protocol_utils
        self._buffer = MessageBuffer()
        self._incomplete_messages: deque = deque()
    
    async def feed_data(self, data: Union[bytes, memoryview]) -> List[Union[BaseRequest, BaseResponse]]:
        """
        输入数据并提取完整消息
        Feed data and extract complete messages
        
        Args:
            data: 接收到的数据
            
        Returns:
            List[Union[BaseRequest, BaseResponse]]: 解析出的完整消息列表
        """
        # 将数据写入缓冲区
        self._buffer.write(data)
        
        messages = []
        
        # 尝试解析所有完整的消息
        while True:
            try:
                frame_result = self._protocol_utils.parse_frame(self._buffer)
                if frame_result is None:
                    break
                
                length, message_data = frame_result
                
                # 解码消息
                message = await self._protocol_utils.decode_message(message_data)
                messages.append(message)
                
            except ProtocolError as e:
                logger.error(f"Protocol error while parsing frame: {e}")
                # 清空缓冲区以恢复
                self._buffer.clear()
                break
        
        # 压缩缓冲区
        self._buffer.compact()
        
        return messages
    
    def get_buffer_size(self) -> int:
        """获取当前缓冲区大小"""
        return len(self._buffer)
    
    def clear(self) -> None:
        """清空缓冲区"""
        self._buffer.clear()


# 创建默认协议工具实例
default_protocol_utils = ProtocolUtils()


async def quick_encode(message: Union[BaseRequest, BaseResponse]) -> bytes:
    """
    快速编码消息（使用默认工具）
    Quick encode message using default utils
    
    Args:
        message: 要编码的消息
        
    Returns:
        bytes: 编码后的数据
    """
    return await default_protocol_utils.encode_message(message)


async def quick_decode(data: Union[bytes, memoryview]) -> Union[BaseRequest, BaseResponse]:
    """
    快速解码消息（使用默认工具）
    Quick decode message using default utils
    
    Args:
        data: 要解码的数据
        
    Returns:
        Union[BaseRequest, BaseResponse]: 解码后的消息
    """
    return await default_protocol_utils.decode_message(data)