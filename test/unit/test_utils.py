"""
统一工具模块单元测试
作者: lx
日期: 2025-06-20
"""
import pytest
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.utils import (
    auto_serialize, auto_deserialize,
    ErrorHandler, ValidationError, Validator,
    retry, timeout
)

class TestSerialization:
    """序列化工具测试"""
    
    def test_msgpack_serialization(self):
        """测试msgpack序列化"""
        data = {"test": "data", "number": 42}
        serialized = auto_serialize(data, "msgpack")
        deserialized = auto_deserialize(serialized, "msgpack")
        
        assert deserialized == data
    
    def test_json_serialization(self):
        """测试JSON序列化"""
        data = {"test": "data", "number": 42}
        serialized = auto_serialize(data, "json")
        deserialized = auto_deserialize(serialized, "json")
        
        assert deserialized == data
    
    def test_invalid_format(self):
        """测试无效格式"""
        with pytest.raises(ValueError):
            auto_serialize({"test": "data"}, "invalid_format")

class TestErrorHandler:
    """错误处理器测试"""
    
    def test_error_handler_creation(self):
        """测试错误处理器创建"""
        handler = ErrorHandler()
        assert handler is not None
    
    def test_handle_error_without_reraise(self):
        """测试错误处理（不重新抛出）"""
        handler = ErrorHandler()
        error = ValueError("test error")
        
        result = handler.handle_error(error, reraise=False)
        
        assert result["error_type"] == "ValueError"
        assert result["error_message"] == "test error"
        assert "traceback" in result

class TestValidator:
    """验证器测试"""
    
    def test_required_validator(self):
        """测试必填验证器"""
        # 正常情况
        assert Validator.required("test") == True
        
        # 异常情况
        with pytest.raises(ValidationError):
            Validator.required(None)
        
        with pytest.raises(ValidationError):
            Validator.required("")
    
    def test_string_length_validator(self):
        """测试字符串长度验证器"""
        # 正常情况
        assert Validator.string_length("test", 1, 10) == True
        
        # 太短
        with pytest.raises(ValidationError):
            Validator.string_length("a", 5, 10)
        
        # 太长
        with pytest.raises(ValidationError):
            Validator.string_length("very long string", 1, 5)
    
    def test_numeric_range_validator(self):
        """测试数值范围验证器"""
        # 正常情况
        assert Validator.numeric_range(5, 1, 10) == True
        
        # 太小
        with pytest.raises(ValidationError):
            Validator.numeric_range(0, 1, 10)
        
        # 太大
        with pytest.raises(ValidationError):
            Validator.numeric_range(15, 1, 10)
    
    def test_player_id_format(self):
        """测试玩家ID格式验证"""
        # 正确格式
        assert Validator.player_id_format("player_1234567890") == True
        
        # 错误格式
        with pytest.raises(ValidationError):
            Validator.player_id_format("invalid_id")

class TestDecorators:
    """装饰器测试"""
    
    @pytest.mark.asyncio
    async def test_retry_decorator_success(self):
        """测试重试装饰器（成功情况）"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        async def test_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await test_function()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_decorator_failure(self):
        """测试重试装饰器（失败情况）"""
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        async def test_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            await test_function()
        
        assert call_count == 3  # 应该重试3次
    
    @pytest.mark.asyncio
    async def test_timeout_decorator(self):
        """测试超时装饰器"""
        @timeout(0.1)
        async def fast_function():
            return "done"
        
        # 快速函数应该正常执行
        result = await fast_function()
        assert result == "done"
        
        @timeout(0.1)
        async def slow_function():
            await asyncio.sleep(0.2)
            return "done"
        
        # 慢函数应该超时
        with pytest.raises(TimeoutError):
            await slow_function()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])