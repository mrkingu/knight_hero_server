"""
gRPC框架测试模块
gRPC Framework Test Module

作者: lx
日期: 2025-06-18
描述: 测试gRPC服务框架的各个组件功能
"""

import pytest
import asyncio
import logging
from typing import Dict, Any

# 设置测试日志
logging.basicConfig(level=logging.DEBUG)

# 导入gRPC框架
from common.grpc import (
    grpc_service, grpc_method, GrpcClient,
    start_grpc_server, register_service_instance,
    get_service_registry, get_connection_pool
)


# 测试服务定义
@grpc_service("test_service", address="localhost", port=50052)
class TestService:
    """测试服务"""
    
    def __init__(self):
        self.call_count = 0
    
    @grpc_method(timeout=2.0, description="基础测试方法")
    async def basic_test(self, message: str) -> Dict[str, Any]:
        """基础测试方法"""
        self.call_count += 1
        await asyncio.sleep(0.01)  # 模拟异步操作
        return {
            "status": "success",
            "message": f"Received: {message}",
            "call_count": self.call_count
        }
    
    @grpc_method(timeout=1.0, description="错误测试方法")
    async def error_test(self) -> None:
        """故意抛出错误的测试方法"""
        raise ValueError("测试错误")
    
    @grpc_method(timeout=0.5, description="超时测试方法")
    async def timeout_test(self) -> str:
        """超时测试方法"""
        await asyncio.sleep(1.0)  # 超过timeout时间
        return "This should not be returned"


class TestGrpcFramework:
    """gRPC框架测试类"""
    
    @pytest.fixture(scope="class")
    async def grpc_server(self):
        """启动测试用的gRPC服务器"""
        # 注册服务实例
        service_instance = TestService()
        register_service_instance("test_service", service_instance)
        
        # 启动服务器
        server = await start_grpc_server("localhost:50052")
        
        # 等待服务器启动
        await asyncio.sleep(0.5)
        
        yield server
        
        # 清理：停止服务器
        await server.stop(grace=1)
    
    @pytest.mark.asyncio
    async def test_service_decorator(self):
        """测试@grpc_service装饰器"""
        # 检查服务是否已注册
        registry = get_service_registry()
        service_info = registry.get_service("test_service")
        
        assert service_info is not None
        assert service_info.name == "test_service"
        assert len(service_info.methods) >= 3  # 至少有3个测试方法
        
        # 检查方法是否已注册
        basic_method = service_info.methods.get("basic_test")
        assert basic_method is not None
        assert basic_method.timeout == 2.0
        assert basic_method.description == "基础测试方法"
    
    @pytest.mark.asyncio
    async def test_method_decorator(self):
        """测试@grpc_method装饰器"""
        registry = get_service_registry()
        service_info = registry.get_service("test_service")
        
        # 检查各种方法配置
        methods = service_info.methods
        
        assert "basic_test" in methods
        assert "error_test" in methods
        assert "timeout_test" in methods
        
        # 检查timeout配置
        assert methods["basic_test"].timeout == 2.0
        assert methods["error_test"].timeout == 1.0
        assert methods["timeout_test"].timeout == 0.5
    
    @pytest.mark.asyncio
    async def test_connection_pool(self):
        """测试连接池功能"""
        pool = get_connection_pool()
        
        # 获取连接
        channel = await pool.get_channel("localhost:50052")
        assert channel is not None
        
        # 检查连接池统计
        stats = pool.get_stats()
        assert "global_stats" in stats
        assert "pool_stats" in stats
        
        # 检查是否有连接池被创建
        pool_stats = stats["pool_stats"]
        assert "localhost:50052" in pool_stats
        assert pool_stats["localhost:50052"]["total_connections"] >= 1
    
    @pytest.mark.asyncio
    async def test_grpc_client_basic(self, grpc_server):
        """测试gRPC客户端基础功能"""
        # 等待服务器启动
        await asyncio.sleep(1.0)
        
        async with GrpcClient("localhost:50052") as client:
            # 测试基础调用 - 使用完整的服务名.方法名格式
            result = await client.call("test_service.basic_test", message="Hello gRPC")
            
            assert result["status"] == "success"
            assert "Hello gRPC" in result["message"]
            assert result["call_count"] == 1
            
            # 测试第二次调用
            result2 = await client.call("test_service.basic_test", message="Second call")
            assert result2["call_count"] == 2
    
    @pytest.mark.asyncio 
    async def test_grpc_client_error_handling(self, grpc_server):
        """测试gRPC客户端错误处理"""
        await asyncio.sleep(1.0)
        
        async with GrpcClient("localhost:50052") as client:
            # 测试服务端错误
            with pytest.raises(Exception):
                await client.call("test_service.error_test")
    
    @pytest.mark.asyncio
    async def test_grpc_client_timeout(self, grpc_server):
        """测试gRPC客户端超时处理"""
        await asyncio.sleep(1.0)
        
        async with GrpcClient("localhost:50052", default_timeout=0.1) as client:
            # 测试超时
            with pytest.raises(asyncio.TimeoutError):
                await client.call("test_service.timeout_test")
    
    @pytest.mark.asyncio
    async def test_client_stats(self, grpc_server):
        """测试客户端统计信息"""
        await asyncio.sleep(1.0)
        
        client = GrpcClient("localhost:50052")
        
        # 执行一些调用
        try:
            await client.call("test_service.basic_test", message="stats test")
        except Exception:
            pass
        
        try:
            await client.call("test_service.error_test")
        except Exception:
            pass
        
        # 检查统计信息
        stats = client.get_stats()
        assert "client_stats" in stats
        assert "circuit_breaker_stats" in stats
        
        client_stats = stats["client_stats"]
        assert client_stats["total_calls"] >= 2
        
        await client.close()


@pytest.mark.asyncio
async def test_framework_integration():
    """测试框架集成功能"""
    # 创建另一个简单的服务来测试集成
    @grpc_service("integration_test")
    class IntegrationTestService:
        @grpc_method
        async def ping(self) -> str:
            return "pong"
    
    # 注册服务
    service = IntegrationTestService()
    register_service_instance("integration_test", service)
    
    # 检查注册状态
    registry = get_service_registry()
    service_info = registry.get_service("integration_test")
    
    assert service_info is not None
    assert service_info.instance is service
    assert "ping" in service_info.methods


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])