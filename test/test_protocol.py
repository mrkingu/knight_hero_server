"""
Protocol协议层测试
Protocol Layer Tests

作者: lx
日期: 2025-06-18
描述: Protocol Buffer协议层的完整单元测试，包括性能测试
"""

import asyncio
import pytest
import time
import os
from pathlib import Path

from common.protocol.base import (
    BaseRequest, BaseResponse, MessagePool, BufferPool, 
    get_pool_stats, create_request_batch, create_response_batch
)
from common.protocol.protocol_utils import (
    ProtocolUtils, MessageBuffer, Encryption, MessageFramer,
    quick_encode, quick_decode, ProtocolError, EncryptionError
)
from common.protocol.proto_gen import (
    AutoProtoGenerator, PythonClassParser, ProtoGenerator, TypeMapping
)


class TestBaseMessage:
    """测试基础消息类"""
    
    def test_base_request_creation(self):
        """测试基础请求创建"""
        request = BaseRequest(player_id="player123", payload=b"test_data", msg_id=1001)
        
        assert request.player_id == "player123"
        assert request.payload == b"test_data"
        assert request.msg_id == 1001
        assert request.sequence > 0
        assert request.timestamp > 0
    
    def test_base_response_creation(self):
        """测试基础响应创建"""
        response = BaseResponse(code=0, message="Success", payload=b"response_data", msg_id=1002)
        
        assert response.code == 0
        assert response.message == "Success"
        assert response.payload == b"response_data"
        assert response.msg_id == 1002
    
    @pytest.mark.asyncio
    async def test_request_serialization(self):
        """测试请求序列化"""
        request = BaseRequest(player_id="player123", payload=b"test_data", msg_id=1001)
        
        # 序列化
        data = await request.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        # 反序列化
        decoded_request = BaseRequest.from_bytes(data)
        assert decoded_request.player_id == request.player_id
        assert decoded_request.payload == request.payload
        assert decoded_request.msg_id == request.msg_id
        assert decoded_request.sequence == request.sequence
    
    @pytest.mark.asyncio
    async def test_response_serialization(self):
        """测试响应序列化"""
        response = BaseResponse(code=0, message="Success", payload=b"response_data", msg_id=1002)
        
        # 序列化
        data = await response.to_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0
        
        # 反序列化
        decoded_response = BaseResponse.from_bytes(data)
        assert decoded_response.code == response.code
        assert decoded_response.message == response.message
        assert decoded_response.payload == response.payload
        assert decoded_response.msg_id == response.msg_id
    
    def test_success_response(self):
        """测试成功响应创建"""
        response = BaseResponse.success(payload=b"success_data", request_sequence=123, msg_id=1003)
        
        assert response.code == 0
        assert response.message == "Success"
        assert response.payload == b"success_data"
        assert response.sequence == 123
        assert response.msg_id == 1003
    
    def test_error_response(self):
        """测试错误响应创建"""
        response = BaseResponse.error(code=400, message="Bad Request", request_sequence=124, msg_id=1004)
        
        assert response.code == 400
        assert response.message == "Bad Request"
        assert response.sequence == 124
        assert response.msg_id == 1004
    
    @pytest.mark.asyncio
    async def test_batch_creation(self):
        """测试批量消息创建"""
        requests = [
            BaseRequest(player_id=f"player{i}", payload=f"data{i}".encode(), msg_id=2000 + i)
            for i in range(10)
        ]
        
        # 批量序列化
        batch_data = await create_request_batch(requests)
        assert len(batch_data) == 10
        assert all(isinstance(data, bytes) for data in batch_data)
        
        responses = [
            BaseResponse.success(payload=f"response{i}".encode(), msg_id=3000 + i)
            for i in range(5)
        ]
        
        # 批量序列化响应
        batch_response_data = await create_response_batch(responses)
        assert len(batch_response_data) == 5
        assert all(isinstance(data, bytes) for data in batch_response_data)


class TestMessagePool:
    """测试消息池"""
    
    def test_message_pool_basic(self):
        """测试消息池基本功能"""
        pool = MessagePool(dict, max_size=5)
        
        # 获取对象
        obj1 = pool.get()
        obj2 = pool.get()
        assert isinstance(obj1, dict)
        assert isinstance(obj2, dict)
        assert obj1 is not obj2
        
        # 归还对象
        pool.put(obj1)
        pool.put(obj2)
        
        # 再次获取应该复用
        obj3 = pool.get()
        assert obj3 is obj2  # 后进先出
    
    def test_buffer_pool_basic(self):
        """测试缓冲区池基本功能"""
        pool = BufferPool(initial_size=1024, max_size=10)
        
        # 获取缓冲区
        buffer1 = pool.get(min_size=512)
        assert isinstance(buffer1, bytearray)
        assert len(buffer1) >= 512
        
        buffer2 = pool.get(min_size=2048)
        assert len(buffer2) >= 2048
        
        # 归还缓冲区
        pool.put(buffer1)
        pool.put(buffer2)
        
        # 再次获取
        buffer3 = pool.get(min_size=1024)
        assert buffer3 is buffer2  # 应该复用较大的缓冲区
    
    def test_pool_stats(self):
        """测试池统计信息"""
        stats = get_pool_stats()
        
        assert 'request_pool' in stats
        assert 'response_pool' in stats
        assert 'buffer_pool_size' in stats
        assert 'message_stats' in stats
        
        message_stats = stats['message_stats']
        assert 'total_encoded' in message_stats
        assert 'total_decoded' in message_stats
        assert 'avg_encode_time_ms' in message_stats
        assert 'avg_decode_time_ms' in message_stats


class TestProtocolUtils:
    """测试协议工具类"""
    
    @pytest.mark.asyncio
    async def test_basic_encode_decode(self):
        """测试基本编解码"""
        utils = ProtocolUtils()
        
        # 创建请求
        request = BaseRequest(player_id="test_player", payload=b"test_payload", msg_id=4001)
        
        # 编码
        encoded_data = await utils.encode_message(request)
        assert isinstance(encoded_data, bytes)
        assert len(encoded_data) > 0
        
        # 解码
        decoded_message = await utils.decode_message(encoded_data)
        assert isinstance(decoded_message, BaseRequest)
        assert decoded_message.player_id == request.player_id
        assert decoded_message.payload == request.payload
        assert decoded_message.msg_id == request.msg_id
    
    @pytest.mark.asyncio
    async def test_encryption_encode_decode(self):
        """测试加密编解码"""
        encryption_key = os.urandom(16)
        utils = ProtocolUtils(enable_encryption=True, encryption_key=encryption_key)
        
        # 创建请求
        request = BaseRequest(player_id="encrypted_player", payload=b"secret_data", msg_id=4002)
        
        # 编码（加密）
        encoded_data = await utils.encode_message(request)
        assert isinstance(encoded_data, bytes)
        
        # 解码（解密）
        decoded_message = await utils.decode_message(encoded_data)
        assert isinstance(decoded_message, BaseRequest)
        assert decoded_message.player_id == request.player_id
        assert decoded_message.payload == request.payload
    
    @pytest.mark.asyncio
    async def test_batch_encode_decode(self):
        """测试批量编解码"""
        utils = ProtocolUtils()
        
        # 创建多个消息
        messages = [
            BaseRequest(player_id=f"player{i}", payload=f"data{i}".encode(), msg_id=5000 + i)
            for i in range(5)
        ]
        
        # 批量编码
        encoded_list = await utils.encode_batch(messages)
        assert len(encoded_list) == 5
        assert all(isinstance(data, bytes) for data in encoded_list)
        
        # 批量解码
        decoded_list = await utils.decode_batch(encoded_list)
        assert len(decoded_list) == 5
        
        for original, decoded in zip(messages, decoded_list):
            assert decoded.player_id == original.player_id
            assert decoded.payload == original.payload
            assert decoded.msg_id == original.msg_id
    
    def test_invalid_data_decode(self):
        """测试无效数据解码"""
        utils = ProtocolUtils()
        
        with pytest.raises(ProtocolError):
            asyncio.run(utils.decode_message(b"invalid_data"))
        
        with pytest.raises(ProtocolError):
            asyncio.run(utils.decode_message(b""))
    
    def test_protocol_stats(self):
        """测试协议统计信息"""
        utils = ProtocolUtils()
        stats = utils.get_stats()
        
        assert 'messages_encoded' in stats
        assert 'messages_decoded' in stats
        assert 'bytes_encoded' in stats
        assert 'bytes_decoded' in stats
        assert 'avg_encode_time_ms' in stats
        assert 'avg_decode_time_ms' in stats
        assert 'encryption_enabled' in stats


class TestMessageBuffer:
    """测试消息缓冲区"""
    
    def test_buffer_write_read(self):
        """测试缓冲区读写"""
        buffer = MessageBuffer(initial_size=1024)
        
        # 写入数据
        test_data = b"Hello, World!"
        written = buffer.write(test_data)
        assert written == len(test_data)
        
        # 读取数据
        read_data = buffer.read(len(test_data))
        assert read_data is not None
        assert bytes(read_data) == test_data
    
    def test_buffer_peek(self):
        """测试缓冲区预览"""
        buffer = MessageBuffer(initial_size=1024)
        
        test_data = b"Test Data"
        buffer.write(test_data)
        
        # 预览数据
        peeked = buffer.peek(4)
        assert peeked is not None
        assert bytes(peeked) == b"Test"
        
        # 确认位置没有移动
        read_data = buffer.read(len(test_data))
        assert bytes(read_data) == test_data
    
    def test_buffer_compact(self):
        """测试缓冲区压缩"""
        buffer = MessageBuffer(initial_size=1024)
        
        # 写入数据
        buffer.write(b"FirstPart")
        buffer.write(b"SecondPart")
        
        # 读取部分数据
        buffer.read(9)  # 读取 "FirstPart"
        
        # 压缩缓冲区
        remaining_before = buffer.remaining()
        buffer.compact()
        
        # 验证压缩后的状态
        read_data = buffer.read(10)  # 读取 "SecondPart"
        assert bytes(read_data) == b"SecondPart"


class TestEncryption:
    """测试加密功能"""
    
    def test_encryption_basic(self):
        """测试基本加密解密"""
        encryption = Encryption()
        
        test_data = b"This is secret data"
        
        # 加密
        encrypted = encryption.encrypt(test_data)
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > len(test_data)  # 包含nonce和tag
        
        # 解密
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == test_data
    
    def test_encryption_with_key(self):
        """测试使用指定密钥加密"""
        key = os.urandom(16)
        encryption = Encryption(key)
        
        assert encryption.key == key
        
        test_data = b"Test with custom key"
        encrypted = encryption.encrypt(test_data)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == test_data
    
    def test_encryption_with_associated_data(self):
        """测试关联数据加密"""
        encryption = Encryption()
        
        test_data = b"Secret message"
        associated_data = b"Public metadata"
        
        # 加密
        encrypted = encryption.encrypt(test_data, associated_data)
        
        # 解密（需要相同的关联数据）
        decrypted = encryption.decrypt(encrypted, associated_data)
        assert decrypted == test_data
        
        # 使用错误的关联数据应该失败
        with pytest.raises(EncryptionError):
            encryption.decrypt(encrypted, b"Wrong metadata")
    
    def test_invalid_key_size(self):
        """测试无效密钥大小"""
        with pytest.raises(EncryptionError):
            Encryption(b"short_key")  # 密钥太短
    
    def test_tampered_data(self):
        """测试篡改数据检测"""
        encryption = Encryption()
        
        test_data = b"Important data"
        encrypted = encryption.encrypt(test_data)
        
        # 篡改数据
        tampered = bytearray(encrypted)
        tampered[-1] ^= 1  # 修改最后一个字节
        
        # 解密应该失败
        with pytest.raises(EncryptionError):
            encryption.decrypt(bytes(tampered))


class TestMessageFramer:
    """测试消息帧处理器"""
    
    @pytest.mark.asyncio
    async def test_complete_message_framing(self):
        """测试完整消息帧处理"""
        utils = ProtocolUtils()
        framer = MessageFramer(utils)
        
        # 创建测试消息
        request = BaseRequest(player_id="frame_test", payload=b"frame_data", msg_id=6001)
        encoded_data = await utils.encode_message(request)
        
        # 一次性输入完整消息
        messages = await framer.feed_data(encoded_data)
        assert len(messages) == 1
        assert messages[0].player_id == request.player_id
        assert messages[0].payload == request.payload
    
    @pytest.mark.asyncio
    async def test_partial_message_framing(self):
        """测试部分消息帧处理"""
        utils = ProtocolUtils()
        framer = MessageFramer(utils)
        
        # 创建测试消息
        request = BaseRequest(player_id="partial_test", payload=b"partial_data", msg_id=6002)
        encoded_data = await utils.encode_message(request)
        
        # 分片输入消息
        mid_point = len(encoded_data) // 2
        
        # 输入前半部分
        messages1 = await framer.feed_data(encoded_data[:mid_point])
        assert len(messages1) == 0  # 不应该有完整消息
        
        # 输入后半部分
        messages2 = await framer.feed_data(encoded_data[mid_point:])
        assert len(messages2) == 1  # 现在应该有一个完整消息
        assert messages2[0].player_id == request.player_id
        assert messages2[0].payload == request.payload
    
    @pytest.mark.asyncio
    async def test_multiple_message_framing(self):
        """测试多消息帧处理"""
        utils = ProtocolUtils()
        framer = MessageFramer(utils)
        
        # 创建多个测试消息
        requests = [
            BaseRequest(player_id=f"multi{i}", payload=f"data{i}".encode(), msg_id=6100 + i)
            for i in range(3)
        ]
        
        # 编码所有消息并连接
        encoded_messages = []
        for request in requests:
            encoded_data = await utils.encode_message(request)
            encoded_messages.append(encoded_data)
        
        combined_data = b''.join(encoded_messages)
        
        # 一次性输入所有数据
        messages = await framer.feed_data(combined_data)
        assert len(messages) == 3
        
        for i, message in enumerate(messages):
            assert message.player_id == f"multi{i}"
            assert message.payload == f"data{i}".encode()
            assert message.msg_id == 6100 + i


class TestPerformance:
    """性能测试"""
    
    @pytest.mark.asyncio
    async def test_encode_decode_performance(self):
        """测试编解码性能，要求<1ms"""
        utils = ProtocolUtils()
        
        # 创建测试消息
        request = BaseRequest(
            player_id="performance_test",
            payload=b"x" * 1000,  # 1KB 数据
            msg_id=7001
        )
        
        # 测试编码性能
        start_time = time.perf_counter()
        encoded_data = await utils.encode_message(request)
        encode_time = (time.perf_counter() - start_time) * 1000  # 转换为毫秒
        
        # 测试解码性能
        start_time = time.perf_counter()
        decoded_message = await utils.decode_message(encoded_data)
        decode_time = (time.perf_counter() - start_time) * 1000  # 转换为毫秒
        
        print(f"Encode time: {encode_time:.3f}ms")
        print(f"Decode time: {decode_time:.3f}ms")
        
        # 验证性能要求 (<1ms)
        assert encode_time < 1.0, f"Encode too slow: {encode_time:.3f}ms"
        assert decode_time < 1.0, f"Decode too slow: {decode_time:.3f}ms"
        
        # 验证数据正确性
        assert decoded_message.player_id == request.player_id
        assert decoded_message.payload == request.payload
    
    @pytest.mark.asyncio
    async def test_batch_performance(self):
        """测试批量处理性能"""
        utils = ProtocolUtils()
        
        # 创建100个消息
        messages = [
            BaseRequest(player_id=f"batch{i}", payload=f"data{i}".encode() * 10, msg_id=8000 + i)
            for i in range(100)
        ]
        
        # 测试批量编码性能
        start_time = time.perf_counter()
        encoded_list = await utils.encode_batch(messages)
        batch_encode_time = (time.perf_counter() - start_time) * 1000
        
        # 测试批量解码性能
        start_time = time.perf_counter()
        decoded_list = await utils.decode_batch(encoded_list)
        batch_decode_time = (time.perf_counter() - start_time) * 1000
        
        print(f"Batch encode time (100 messages): {batch_encode_time:.3f}ms")
        print(f"Batch decode time (100 messages): {batch_decode_time:.3f}ms")
        print(f"Average encode time per message: {batch_encode_time/100:.3f}ms")
        print(f"Average decode time per message: {batch_decode_time/100:.3f}ms")
        
        # 验证批量处理平均性能仍然 <1ms per message
        assert batch_encode_time / 100 < 1.0
        assert batch_decode_time / 100 < 1.0
        
        # 验证数据正确性
        assert len(decoded_list) == 100
        for i, decoded in enumerate(decoded_list):
            assert decoded.player_id == f"batch{i}"
            assert decoded.payload == f"data{i}".encode() * 10


class TestQuickAPI:
    """测试快速API"""
    
    @pytest.mark.asyncio
    async def test_quick_encode_decode(self):
        """测试快速编解码API"""
        request = BaseRequest(player_id="quick_test", payload=b"quick_data", msg_id=9001)
        
        # 快速编码
        encoded_data = await quick_encode(request)
        assert isinstance(encoded_data, bytes)
        
        # 快速解码
        decoded_message = await quick_decode(encoded_data)
        assert decoded_message.player_id == request.player_id
        assert decoded_message.payload == request.payload
        assert decoded_message.msg_id == request.msg_id


class TestTypeMapping:
    """测试类型映射"""
    
    def test_basic_type_mapping(self):
        """测试基本类型映射"""
        assert TypeMapping.map_type('int') == 'int32'
        assert TypeMapping.map_type('float') == 'float'
        assert TypeMapping.map_type('str') == 'string'
        assert TypeMapping.map_type('bool') == 'bool'
        assert TypeMapping.map_type('bytes') == 'bytes'
    
    def test_list_type_mapping(self):
        """测试列表类型映射"""
        assert TypeMapping.map_type('List[int]') == 'repeated int32'
        assert TypeMapping.map_type('List[str]') == 'repeated string'
        assert TypeMapping.map_type('List[bool]') == 'repeated bool'
    
    def test_optional_type_mapping(self):
        """测试可选类型映射"""
        assert TypeMapping.map_type('Optional[int]') == 'int32'
        assert TypeMapping.map_type('Optional[str]') == 'string'
        assert TypeMapping.map_type('Optional[bool]') == 'bool'


class TestProtoGenerator:
    """测试Proto生成器"""
    
    def test_proto_content_generation(self):
        """测试Proto内容生成"""
        from common.protocol.proto_gen import MessageInfo, FieldInfo
        
        # 创建测试消息信息
        field1 = FieldInfo(name="id", type_name="int32", field_number=1)
        field2 = FieldInfo(name="name", type_name="string", field_number=2)
        field3 = FieldInfo(name="tags", type_name="repeated string", field_number=3)
        
        message = MessageInfo(
            name="TestMessage",
            fields=[field1, field2, field3],
            comment="Test message for generation"
        )
        
        generator = ProtoGenerator("test.protocol")
        content = generator.generate_proto_content([message])
        
        assert 'syntax = "proto3"' in content
        assert 'package test.protocol' in content
        assert 'message TestMessage' in content
        assert 'int32 id = 1' in content
        assert 'string name = 2' in content
        assert 'repeated string tags = 3' in content


if __name__ == '__main__':
    # 运行性能测试
    pytest.main([__file__ + "::TestPerformance", "-v", "-s"])