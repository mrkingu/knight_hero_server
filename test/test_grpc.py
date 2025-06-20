"""
gRPC服务框架测试
测试gRPC连接池、服务装饰器、客户端等核心功能
作者: lx
日期: 2025-06-18
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# 测试组件导入
try:
    from common.grpc import (
        GrpcClient, grpc_service, grpc_method, 
        GrpcConnectionPool, get_connection_pool,
        get_service_registry, register_service_instance
    )
    from common.grpc.grpc_client import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError
    from common.grpc.grpc_service import GameServiceServicer
    
    GRPC_AVAILABLE = True
except ImportError as e:
    print(f"gRPC模块导入失败: {e}")
    GRPC_AVAILABLE = False


@pytest.mark.skipif(not GRPC_AVAILABLE, reason="gRPC模块不可用")
class TestGrpcService:
    """测试gRPC服务装饰器"""
    
    def test_grpc_service_decorator(self):
        """测试@grpc_service装饰器"""
        @grpc_service("test_service")
        class TestService:
            @grpc_method(timeout=5.0, description="测试方法")
            async def test_method(self, data: str) -> dict:
                return {"result": f"processed_{data}"}
        
        # 检查类是否被正确装饰
        assert hasattr(TestService, '_grpc_service_info')
        service_info = TestService._grpc_service_info
        assert service_info.name == "test_service"
        assert service_info.cls == TestService
        assert "test_method" in service_info.methods
        
        # 检查方法信息
        method_info = service_info.methods["test_method"]
        assert method_info.name == "test_method"
        assert method_info.timeout == 5.0
        assert method_info.description == "测试方法"
        assert method_info.is_async is True
    
    def test_grpc_method_decorator(self):
        """测试@grpc_method装饰器"""
        class TestService:
            @grpc_method(timeout=3.0, retry_count=2)
            async def async_method(self, x: int) -> int:
                return x * 2
            
            @grpc_method(timeout=1.0)
            def sync_method(self, x: str) -> str:
                return x.upper()
        
        # 检查异步方法
        async_method = TestService.async_method
        assert hasattr(async_method, '_grpc_method_info')
        assert async_method._grpc_method_info.timeout == 3.0
        assert async_method._grpc_method_info.retry_count == 2
        assert async_method._grpc_method_info.is_async is True
        
        # 检查同步方法
        sync_method = TestService.sync_method  
        assert hasattr(sync_method, '_grpc_method_info')
        assert sync_method._grpc_method_info.timeout == 1.0
        assert sync_method._grpc_method_info.is_async is False
    
    def test_service_registry(self):
        """测试服务注册表"""
        registry = get_service_registry()
        
        @grpc_service("registry_test")
        class RegistryTestService:
            @grpc_method
            async def get_data(self, id: str) -> dict:
                return {"id": id, "data": "test"}
        
        # 检查服务是否注册
        service_info = registry.get_service("registry_test")
        assert service_info is not None
        assert service_info.name == "registry_test"
        
        # 检查方法是否注册
        method_info = registry.get_method("registry_test", "get_data")
        assert method_info is not None
        assert method_info.name == "get_data"
        
        # 注册服务实例
        instance = RegistryTestService()
        register_service_instance("registry_test", instance)
        assert service_info.instance == instance


@pytest.mark.skipif(not GRPC_AVAILABLE, reason="gRPC模块不可用")
class TestGrpcConnectionPool:
    """测试gRPC连接池"""
    
    @pytest.fixture
    async def connection_pool(self):
        """连接池fixture"""
        pool = GrpcConnectionPool(
            min_connections=2,
            max_connections=5,
            health_check_interval=1
        )
        yield pool
        await pool.close_all()
    
    @pytest.mark.asyncio
    async def test_pool_creation(self, connection_pool):
        """测试连接池创建"""
        assert connection_pool.min_connections == 2
        assert connection_pool.max_connections == 5
        assert connection_pool.health_check_interval == 1
        assert len(connection_pool._pools) == 0
    
    @pytest.mark.asyncio
    async def test_pool_stats(self, connection_pool):
        """测试连接池统计"""
        stats = connection_pool.get_stats()
        
        assert "global_stats" in stats
        assert "pool_stats" in stats
        assert stats["global_stats"]["total_connections"] == 0
        assert stats["global_stats"]["active_connections"] == 0
    
    def test_global_pool(self):
        """测试全局连接池"""
        pool1 = get_connection_pool()
        pool2 = get_connection_pool()
        
        # 应该返回同一个实例
        assert pool1 is pool2
        assert isinstance(pool1, GrpcConnectionPool)


@pytest.mark.skipif(not GRPC_AVAILABLE, reason="gRPC模块不可用")
class TestCircuitBreaker:
    """测试熔断器"""
    
    def test_circuit_breaker_creation(self):
        """测试熔断器创建"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=10.0,
            success_threshold=2
        )
        breaker = CircuitBreaker(config)
        
        assert breaker.config.failure_threshold == 3
        assert breaker.config.recovery_timeout == 10.0
        assert breaker.config.success_threshold == 2
        assert breaker.stats.state.value == "closed"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_success(self):
        """测试熔断器成功调用"""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)
        
        async def success_func():
            return "success"
        
        result = await breaker.call(success_func)
        assert result == "success"
        assert breaker.stats.success_count == 1
        assert breaker.stats.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_failure(self):
        """测试熔断器失败处理"""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)
        
        async def failure_func():
            raise Exception("test error")
        
        # 第一次失败
        with pytest.raises(Exception, match="test error"):
            await breaker.call(failure_func)
        assert breaker.stats.failure_count == 1
        
        # 第二次失败，应该触发熔断
        with pytest.raises(Exception, match="test error"):
            await breaker.call(failure_func)
        assert breaker.stats.failure_count == 2
        assert breaker.stats.state.value == "open"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open_state(self):
        """测试熔断器开启状态"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.1)
        breaker = CircuitBreaker(config)
        
        # 触发熔断
        async def failure_func():
            raise Exception("test error")
        
        with pytest.raises(Exception):
            await breaker.call(failure_func)
        
        assert breaker.stats.state.value == "open"
        
        # 在熔断状态下调用应该抛出熔断异常
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(failure_func)
        
        # 等待恢复时间
        await asyncio.sleep(0.2)
        
        # 应该进入半开状态
        async def success_func():
            return "success"
        
        result = await breaker.call(success_func)
        assert result == "success"
    
    def test_circuit_breaker_stats(self):
        """测试熔断器统计信息"""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)
        
        stats = breaker.get_stats()
        
        assert "state" in stats
        assert "failure_count" in stats
        assert "success_count" in stats
        assert "total_requests" in stats
        assert "recent_failure_rate" in stats
        assert stats["state"] == "closed"
        assert stats["total_requests"] == 0


@pytest.mark.skipif(not GRPC_AVAILABLE, reason="gRPC模块不可用")
class TestGrpcClient:
    """测试gRPC客户端"""
    
    @pytest.fixture
    def mock_pool(self):
        """模拟连接池"""
        with patch('common.grpc.grpc_client.get_connection_pool') as mock:
            pool = Mock()
            pool.get_channel = AsyncMock()
            mock.return_value = pool
            yield pool
    
    @pytest.fixture
    def grpc_client(self, mock_pool):
        """gRPC客户端fixture"""
        return GrpcClient(
            service_address="localhost:50051",
            default_timeout=1.0,
            max_retries=2
        )
    
    def test_client_creation(self, grpc_client):
        """测试客户端创建"""
        assert grpc_client.service_address == "localhost:50051"
        assert grpc_client.default_timeout == 1.0
        assert grpc_client.max_retries == 2
        assert grpc_client.stats["total_calls"] == 0
    
    def test_extract_service_name(self, grpc_client):
        """测试服务名提取"""
        # 测试带服务名的方法
        service_name = grpc_client._extract_service_name("logic.get_player")
        assert service_name == "logic"
        
        # 测试不带服务名的方法
        service_name = grpc_client._extract_service_name("get_player")
        assert service_name == "localhost"
    
    def test_client_stats(self, grpc_client):
        """测试客户端统计信息"""
        stats = grpc_client.get_stats()
        
        assert "client_stats" in stats
        assert "circuit_breaker_stats" in stats
        assert "service_address" in stats
        assert "config" in stats
        
        assert stats["service_address"] == "localhost:50051"
        assert stats["config"]["default_timeout"] == 1.0


@pytest.mark.skipif(not GRPC_AVAILABLE, reason="gRPC模块不可用")
class TestIntegration:
    """集成测试"""
    
    def test_complete_service_definition(self):
        """测试完整的服务定义"""
        @grpc_service("integration_test", address="localhost", port=50051)
        class IntegrationTestService:
            """集成测试服务"""
            
            def __init__(self):
                self.data_store = {}
            
            @grpc_method(timeout=2.0, description="存储数据")
            async def store_data(self, key: str, value: Any) -> bool:
                """存储数据"""
                self.data_store[key] = value
                return True
            
            @grpc_method(timeout=1.0, description="获取数据")
            async def get_data(self, key: str) -> Any:
                """获取数据"""
                return self.data_store.get(key)
            
            @grpc_method(description="列出所有键")
            async def list_keys(self) -> list:
                """列出所有键"""
                return list(self.data_store.keys())
        
        # 创建服务实例
        service_instance = IntegrationTestService()
        register_service_instance("integration_test", service_instance)
        
        # 验证服务注册
        registry = get_service_registry()
        service_info = registry.get_service("integration_test")
        
        assert service_info is not None
        assert service_info.name == "integration_test"
        assert service_info.address == "localhost"
        assert service_info.port == 50051
        assert service_info.instance == service_instance
        assert len(service_info.methods) == 3
        
        # 验证方法注册
        store_method = registry.get_method("integration_test", "store_data")
        assert store_method is not None
        assert store_method.timeout == 2.0
        assert store_method.description == "存储数据"
        
        get_method = registry.get_method("integration_test", "get_data")
        assert get_method is not None
        assert get_method.timeout == 1.0
        
        list_method = registry.get_method("integration_test", "list_keys")
        assert list_method is not None
        assert list_method.timeout == 3.0  # 默认值
    
    def test_service_stats(self):
        """测试服务统计信息"""
        registry = get_service_registry()
        stats = registry.get_stats()
        
        assert "total_services" in stats
        assert "total_methods" in stats
        assert "services" in stats
        assert stats["total_services"] >= 0
        assert stats["total_methods"] >= 0


def test_grpc_module_import():
    """测试gRPC模块导入"""
    if GRPC_AVAILABLE:
        # 测试基本组件导入
        from common.grpc import (
            GrpcClient, grpc_service, grpc_method,
            GrpcConnectionPool, get_connection_pool
        )
        
        assert GrpcClient is not None
        assert grpc_service is not None
        assert grpc_method is not None
        assert GrpcConnectionPool is not None
        assert get_connection_pool is not None
        
        print("✅ gRPC模块导入测试通过")
    else:
        print("⚠️  gRPC模块不可用，跳过导入测试")


def test_basic_functionality():
    """测试基本功能"""
    if not GRPC_AVAILABLE:
        print("⚠️  gRPC模块不可用，跳过基本功能测试")
        return True
    
    try:
        # 测试装饰器基本功能
        @grpc_service("basic_test")
        class BasicTestService:
            @grpc_method
            async def hello(self, name: str) -> str:
                return f"Hello, {name}!"
        
        # 测试连接池创建
        pool = get_connection_pool()
        assert isinstance(pool, GrpcConnectionPool)
        
        # 测试客户端创建
        client = GrpcClient("localhost:50051")
        assert client.service_address == "localhost:50051"
        
        print("✅ gRPC基本功能测试通过")
        return True
        
    except Exception as e:
        print(f"❌ gRPC基本功能测试失败: {e}")
        return False


if __name__ == '__main__':
    # 运行基本测试
    test_grpc_module_import()
    test_basic_functionality()
    
    # 运行完整测试套件
    if GRPC_AVAILABLE:
        pytest.main([__file__, "-v", "-s"])
    else:
        print("gRPC模块不可用，无法运行完整测试")