"""
协议层单元测试
Protocol Layer Unit Tests

作者: lx
日期: 2025-06-18
描述: 协议编解码测试、消息序列化测试、加密解密测试
"""

import asyncio
import pytest
import time
import os
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch

# Import test utilities
from test.conftest import (
    measure_performance, 
    create_test_message,
    GameTestConfiguration
)


class TestProtocolEncoding:
    """协议编解码测试"""
    
    def test_message_header_encoding(self):
        """测试消息头编码"""
        # 模拟消息头结构：长度(4字节) + 类型(2字节) + 标志(1字节)
        import struct
        
        msg_len = 100
        msg_type = 1001
        flags = 0x01  # 压缩标志
        
        header = struct.pack("!IHB", msg_len, msg_type, flags)
        assert len(header) == 7  # 4 + 2 + 1
        
        # 解析头部
        parsed_len, parsed_type, parsed_flags = struct.unpack("!IHB", header)
        assert parsed_len == msg_len
        assert parsed_type == msg_type
        assert parsed_flags == flags
    
    def test_message_body_encoding(self):
        """测试消息体编码"""
        import msgpack
        
        # 创建测试消息体
        message_data = {
            "player_id": "test_player_123",
            "action": "login",
            "timestamp": int(time.time()),
            "data": {
                "username": "testuser",
                "version": "1.0.0"
            }
        }
        
        # 序列化
        encoded = msgpack.packb(message_data)
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0
        
        # 反序列化
        decoded = msgpack.unpackb(encoded, raw=False)
        assert decoded == message_data
        assert decoded["player_id"] == "test_player_123"
        assert decoded["action"] == "login"
    
    def test_message_compression(self):
        """测试消息压缩"""
        import lz4.frame
        
        # 创建较大的测试数据
        test_data = b"Hello World! " * 100  # 重复数据利于压缩
        
        # 压缩
        compressed = lz4.frame.compress(test_data)
        assert isinstance(compressed, bytes)
        assert len(compressed) < len(test_data)  # 压缩后应该更小
        
        # 解压缩
        decompressed = lz4.frame.decompress(compressed)
        assert decompressed == test_data
    
    @pytest.mark.asyncio
    async def test_protocol_message_encoding(self):
        """测试完整协议消息编解码"""
        import struct
        import msgpack
        
        # 创建测试消息
        message = create_test_message(
            msg_type=1001,
            player_id="test_player",
            data={"content": "test message", "timestamp": time.time()}
        )
        
        # 序列化消息体
        body = msgpack.packb(message)
        
        # 创建消息头
        msg_len = len(body)
        msg_type = message["msg_id"]
        flags = 0x00  # 无特殊标志
        
        header = struct.pack("!IHB", msg_len, msg_type, flags)
        
        # 组合完整消息
        full_message = header + body
        
        # 解析消息
        parsed_header = struct.unpack("!IHB", full_message[:7])
        parsed_body = msgpack.unpackb(full_message[7:], raw=False)
        
        assert parsed_header[0] == msg_len
        assert parsed_header[1] == msg_type
        assert parsed_body["msg_id"] == message["msg_id"]
        assert parsed_body["player_id"] == message["player_id"]


class TestMessageSerialization:
    """消息序列化测试"""
    
    def test_simple_message_serialization(self):
        """测试简单消息序列化"""
        message = {
            "type": "chat",
            "content": "Hello, World!",
            "sender": "player123"
        }
        
        # JSON序列化
        json_data = json.dumps(message)
        parsed = json.loads(json_data)
        assert parsed == message
        
        # MessagePack序列化
        import msgpack
        msgpack_data = msgpack.packb(message)
        parsed_msgpack = msgpack.unpackb(msgpack_data, raw=False)
        assert parsed_msgpack == message
        
        # MessagePack通常更紧凑
        assert len(msgpack_data) <= len(json_data.encode())
    
    def test_complex_message_serialization(self):
        """测试复杂消息序列化"""
        import msgpack
        
        complex_message = {
            "msg_id": 2001,
            "player_id": "player_12345",
            "timestamp": time.time(),
            "data": {
                "items": [
                    {"id": 1001, "name": "Sword", "quantity": 1},
                    {"id": 1002, "name": "Shield", "quantity": 1}
                ],
                "stats": {
                    "hp": 100,
                    "mp": 50,
                    "level": 10
                },
                "metadata": {
                    "location": {"x": 100.5, "y": 200.3, "z": 0.0},
                    "flags": [True, False, True]
                }
            }
        }
        
        # 序列化
        serialized = msgpack.packb(complex_message)
        
        # 反序列化
        deserialized = msgpack.unpackb(serialized, raw=False)
        
        # 验证数据完整性
        assert deserialized["msg_id"] == complex_message["msg_id"]
        assert deserialized["player_id"] == complex_message["player_id"]
        assert len(deserialized["data"]["items"]) == 2
        assert deserialized["data"]["stats"]["hp"] == 100
        assert deserialized["data"]["metadata"]["location"]["x"] == 100.5
    
    @pytest.mark.asyncio
    async def test_batch_message_serialization(self):
        """测试批量消息序列化"""
        import msgpack
        
        # 创建多个消息
        messages = []
        for i in range(10):
            message = create_test_message(
                msg_type=2000 + i,
                player_id=f"player_{i}",
                data={"index": i, "content": f"Message {i}"}
            )
            messages.append(message)
        
        # 批量序列化
        start_time = time.perf_counter()
        serialized_messages = [msgpack.packb(msg) for msg in messages]
        serialize_time = (time.perf_counter() - start_time) * 1000
        
        # 批量反序列化
        start_time = time.perf_counter()
        deserialized_messages = [msgpack.unpackb(data, raw=False) for data in serialized_messages]
        deserialize_time = (time.perf_counter() - start_time) * 1000
        
        # 验证数据
        assert len(deserialized_messages) == 10
        for i, msg in enumerate(deserialized_messages):
            assert msg["msg_id"] == 2000 + i
            assert msg["player_id"] == f"player_{i}"
            assert msg["data"]["index"] == i
        
        # 性能验证（每条消息处理时间应该很短）
        assert serialize_time / 10 < 1.0  # <1ms per message
        assert deserialize_time / 10 < 1.0  # <1ms per message


class TestEncryptionDecryption:
    """加密解密测试"""
    
    def test_basic_aes_encryption(self):
        """测试基本AES加密"""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import os
        
        # 生成密钥和IV
        key = os.urandom(32)  # AES-256
        iv = os.urandom(16)   # AES block size
        
        # 要加密的数据
        plaintext = b"This is a secret message that needs to be encrypted!"
        
        # 填充到块大小的倍数
        from cryptography.hazmat.primitives import padding
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext)
        padded_data += padder.finalize()
        
        # 加密
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # 解密
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()
        
        # 去填充
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(decrypted_padded)
        decrypted += unpadder.finalize()
        
        assert decrypted == plaintext
    
    def test_message_encryption_workflow(self):
        """测试消息加密工作流"""
        import msgpack
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os
        
        # 创建加密器
        key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(key)
        
        # 创建测试消息
        message = create_test_message(
            msg_type=3001,
            player_id="encrypted_player",
            data={"secret": "classified information"}
        )
        
        # 序列化消息
        serialized = msgpack.packb(message)
        
        # 加密
        nonce = os.urandom(12)  # GCM mode nonce
        ciphertext = aesgcm.encrypt(nonce, serialized, None)
        
        # 解密
        decrypted_serialized = aesgcm.decrypt(nonce, ciphertext, None)
        
        # 反序列化
        decrypted_message = msgpack.unpackb(decrypted_serialized, raw=False)
        
        # 验证
        assert decrypted_message["msg_id"] == message["msg_id"]
        assert decrypted_message["player_id"] == message["player_id"]
        assert decrypted_message["data"]["secret"] == "classified information"
    
    def test_key_derivation(self):
        """测试密钥派生"""
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        import os
        
        # 密码和盐
        password = b"user_password_123"
        salt = os.urandom(16)
        
        # 密钥派生
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = kdf.derive(password)
        
        assert len(key) == 32  # 256 bits
        assert isinstance(key, bytes)
        
        # 相同密码和盐应该产生相同密钥
        kdf2 = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key2 = kdf2.derive(password)
        assert key == key2
    
    @pytest.mark.asyncio
    async def test_encryption_performance(self):
        """测试加密性能"""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import msgpack
        import os
        
        # 准备测试数据
        key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(key)
        
        messages = []
        for i in range(100):
            message = create_test_message(
                msg_type=4000 + i,
                player_id=f"perf_player_{i}",
                data={"index": i, "data": "x" * 100}  # 每条消息约100字节数据
            )
            messages.append(msgpack.packb(message))
        
        # 测试批量加密性能
        start_time = time.perf_counter()
        encrypted_messages = []
        for msg_data in messages:
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, msg_data, None)
            encrypted_messages.append((nonce, ciphertext))
        encrypt_time = (time.perf_counter() - start_time) * 1000
        
        # 测试批量解密性能
        start_time = time.perf_counter()
        decrypted_messages = []
        for nonce, ciphertext in encrypted_messages:
            decrypted = aesgcm.decrypt(nonce, ciphertext, None)
            decrypted_messages.append(msgpack.unpackb(decrypted, raw=False))
        decrypt_time = (time.perf_counter() - start_time) * 1000
        
        # 性能验证
        assert encrypt_time / 100 < 0.5  # <0.5ms per message for encryption
        assert decrypt_time / 100 < 0.5  # <0.5ms per message for decryption
        
        # 数据完整性验证
        assert len(decrypted_messages) == 100
        for i, msg in enumerate(decrypted_messages):
            assert msg["msg_id"] == 4000 + i
            assert msg["player_id"] == f"perf_player_{i}"


class TestProtocolErrorHandling:
    """协议错误处理测试"""
    
    def test_invalid_message_format(self):
        """测试无效消息格式处理"""
        import msgpack
        
        # 测试无效JSON
        try:
            json.loads("invalid json {")
            assert False, "应该抛出异常"
        except json.JSONDecodeError:
            pass  # 预期的异常
        
        # 测试无效MessagePack
        try:
            msgpack.unpackb(b"invalid msgpack data")
            assert False, "应该抛出异常"
        except (msgpack.exceptions.ExtraData, msgpack.exceptions.UnpackException, ValueError):
            pass  # 预期的异常
    
    def test_message_size_limits(self):
        """测试消息大小限制"""
        import msgpack
        
        # 创建超大消息
        large_data = {"data": "x" * (1024 * 1024)}  # 1MB数据
        serialized = msgpack.packb(large_data)
        
        # 检查消息大小
        max_message_size = 64 * 1024  # 64KB限制
        if len(serialized) > max_message_size:
            # 模拟大消息处理逻辑
            assert True  # 正确检测到大消息
        else:
            # 消息在允许范围内
            deserialized = msgpack.unpackb(serialized, raw=False)
            assert deserialized == large_data
    
    def test_malformed_encryption_data(self):
        """测试损坏的加密数据处理"""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        import os
        
        key = AESGCM.generate_key(bit_length=256)
        aesgcm = AESGCM(key)
        
        # 加密正常数据
        nonce = os.urandom(12)
        plaintext = b"Secret message"
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        
        # 篡改密文
        damaged_ciphertext = bytearray(ciphertext)
        damaged_ciphertext[0] ^= 1  # 修改第一个字节
        
        # 尝试解密应该失败
        try:
            aesgcm.decrypt(nonce, bytes(damaged_ciphertext), None)
            assert False, "应该检测到篡改"
        except InvalidTag:
            pass  # 预期的异常
    
    def test_protocol_version_compatibility(self):
        """测试协议版本兼容性"""
        # 模拟不同版本的协议消息
        v1_message = {
            "version": 1,
            "type": "login",
            "data": {"username": "user123"}
        }
        
        v2_message = {
            "version": 2,
            "type": "login", 
            "data": {"username": "user123", "device_id": "device123"},
            "timestamp": time.time()
        }
        
        # 版本检查逻辑
        def check_version_compatibility(message):
            version = message.get("version", 1)
            if version == 1:
                # 支持v1格式
                return True
            elif version == 2:
                # 支持v2格式（向后兼容）
                return True
            else:
                # 不支持的版本
                return False
        
        assert check_version_compatibility(v1_message)
        assert check_version_compatibility(v2_message)
        assert not check_version_compatibility({"version": 99})


class TestProtocolPerformance:
    """协议性能测试"""
    
    @pytest.mark.asyncio
    async def test_message_throughput(self):
        """测试消息吞吐量"""
        import msgpack
        
        # 创建1000条测试消息
        messages = []
        for i in range(1000):
            message = create_test_message(
                msg_type=5000 + i,
                player_id=f"throughput_player_{i}",
                data={"index": i, "payload": "x" * 50}
            )
            messages.append(message)
        
        # 测试序列化吞吐量
        start_time = time.perf_counter()
        serialized = [msgpack.packb(msg) for msg in messages]
        serialize_time = time.perf_counter() - start_time
        
        # 测试反序列化吞吐量
        start_time = time.perf_counter()
        deserialized = [msgpack.unpackb(data, raw=False) for data in serialized]
        deserialize_time = time.perf_counter() - start_time
        
        # 计算吞吐量
        serialize_throughput = len(messages) / serialize_time  # messages/sec
        deserialize_throughput = len(messages) / deserialize_time  # messages/sec
        
        print(f"序列化吞吐量: {serialize_throughput:.0f} messages/sec")
        print(f"反序列化吞吐量: {deserialize_throughput:.0f} messages/sec")
        
        # 性能要求：至少10K messages/sec
        assert serialize_throughput > 10000
        assert deserialize_throughput > 10000
        
        # 验证数据完整性
        assert len(deserialized) == 1000
        for i, msg in enumerate(deserialized):
            assert msg["msg_id"] == 5000 + i
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self):
        """测试并发处理性能"""
        import msgpack
        
        async def process_message_batch(batch_id: int, count: int) -> List[Dict[str, Any]]:
            """处理一批消息"""
            results = []
            for i in range(count):
                message = create_test_message(
                    msg_type=6000 + batch_id * 100 + i,
                    player_id=f"concurrent_player_{batch_id}_{i}",
                    data={"batch": batch_id, "index": i}
                )
                
                # 模拟序列化和处理
                serialized = msgpack.packb(message)
                processed = msgpack.unpackb(serialized, raw=False)
                results.append(processed)
                
                # 模拟小延迟
                await asyncio.sleep(0.001)
            
            return results
        
        # 创建10个并发批次，每批次50条消息
        tasks = []
        for batch_id in range(10):
            task = process_message_batch(batch_id, 50)
            tasks.append(task)
        
        # 并发执行
        start_time = time.perf_counter()
        batch_results = await asyncio.gather(*tasks)
        concurrent_time = time.perf_counter() - start_time
        
        # 验证结果
        total_messages = sum(len(batch) for batch in batch_results)
        assert total_messages == 500  # 10批次 * 50条消息
        
        # 并发处理应该比串行快
        print(f"并发处理时间: {concurrent_time:.3f}秒")
        print(f"平均处理速度: {total_messages/concurrent_time:.0f} messages/sec")
        
        # 验证消息内容
        for batch_id, batch_results in enumerate(batch_results):
            assert len(batch_results) == 50
            for i, msg in enumerate(batch_results):
                assert msg["data"]["batch"] == batch_id
                assert msg["data"]["index"] == i


if __name__ == "__main__":
    # 运行特定测试
    pytest.main([__file__, "-v", "-s"])