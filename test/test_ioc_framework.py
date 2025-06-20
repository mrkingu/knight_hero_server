"""
IoC容器框架单元测试
IoC Container Framework Unit Tests

作者: mrkingu
日期: 2025-06-20
描述: 测试IoC容器的核心功能：服务注册、依赖注入、生命周期管理
"""

import pytest
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.ioc import (
    service, repository, autowired, BaseService, ServiceContainer,
    ServiceScanner, ServiceNotFoundException, CircularDependencyException
)
from common.ioc.decorators import clear_registry
from common.ioc.exceptions import ContainerException


class TestIoCFramework:
    """IoC框架核心功能测试"""
    
    def setup_method(self):
        """每个测试方法执行前清理注册表"""
        clear_registry()
    
    @pytest.mark.asyncio
    async def test_service_registration_and_injection(self):
        """测试基本的服务注册和依赖注入"""
        
        # 定义测试服务
        @repository("TestRepository")
        class TestRepository(BaseService):
            async def on_initialize(self):
                self.data = {"test": "data"}
                
            def get_data(self):
                return self.data
        
        @service("TestService")
        class TestService(BaseService):
            @autowired("TestRepository")
            def test_repository(self):
                pass
            
            async def on_initialize(self):
                self.initialized = True
                
            def get_test_data(self):
                return self.test_repository.get_data()
        
        # 创建容器并初始化
        container = ServiceContainer()
        
        # 手动注册服务（模拟扫描结果）
        from common.ioc.decorators import get_registered_services
        from common.ioc.base_service import ServiceMetadata
        from common.ioc.decorators import scan_dependencies
        
        registry = get_registered_services()
        for service_name, service_info in registry.items():
            dependencies = scan_dependencies(service_info['class'])
            metadata = ServiceMetadata(
                name=service_name,
                service_class=service_info['class'],
                service_type=service_info['type'],
                singleton=service_info['singleton'],
                dependencies=dependencies
            )
            container.register_service(metadata)
        
        await container.initialize()
        
        # 验证服务可以获取
        test_service = container.get_service("TestService")
        assert test_service is not None
        assert hasattr(test_service, 'initialized')
        assert test_service.initialized is True
        
        # 验证依赖注入工作正常
        test_data = test_service.get_test_data()
        assert test_data == {"test": "data"}
        
        # 清理
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self):
        """测试循环依赖检测"""
        
        @service("ServiceA")
        class ServiceA(BaseService):
            @autowired("ServiceB")
            def service_b(self):
                pass
        
        @service("ServiceB") 
        class ServiceB(BaseService):
            @autowired("ServiceA")
            def service_a(self):
                pass
        
        container = ServiceContainer()
        
        # 手动注册服务
        from common.ioc.decorators import get_registered_services
        from common.ioc.base_service import ServiceMetadata
        from common.ioc.decorators import scan_dependencies
        
        registry = get_registered_services()
        for service_name, service_info in registry.items():
            dependencies = scan_dependencies(service_info['class'])
            metadata = ServiceMetadata(
                name=service_name,
                service_class=service_info['class'],
                service_type=service_info['type'],
                singleton=service_info['singleton'],
                dependencies=dependencies
            )
            container.register_service(metadata)
        
        # 应该抛出循环依赖异常
        with pytest.raises(ContainerException) as exc_info:
            await container.initialize()
        
        # 验证是循环依赖异常
        assert "Circular dependency detected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_service_not_found(self):
        """测试服务未找到异常"""
        
        container = ServiceContainer()
        await container.initialize()
        
        with pytest.raises(ServiceNotFoundException):
            container.get_service("NonExistentService")
        
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """测试服务生命周期管理"""
        
        lifecycle_events = []
        
        # Import decorators to avoid scope issues
        from common.ioc import service
        
        @service("LifecycleService")
        class LifecycleService(BaseService):
            async def on_initialize(self):
                lifecycle_events.append("initialized")
                
            async def on_shutdown(self):
                lifecycle_events.append("shutdown")
        
        container = ServiceContainer()
        
        # 手动注册服务
        from common.ioc.decorators import get_registered_services
        from common.ioc.base_service import ServiceMetadata
        from common.ioc.decorators import scan_dependencies
        
        registry = get_registered_services()
        for service_name, service_info in registry.items():
            dependencies = scan_dependencies(service_info['class'])
            metadata = ServiceMetadata(
                name=service_name,
                service_class=service_info['class'],
                service_type=service_info['type'],
                singleton=service_info['singleton'],
                dependencies=dependencies
            )
            container.register_service(metadata)
        
        await container.initialize()
        
        # 验证初始化被调用
        assert "initialized" in lifecycle_events
        
        service = container.get_service("LifecycleService")
        assert service.is_initialized()
        
        await container.shutdown()
        
        # 验证关闭被调用
        assert "shutdown" in lifecycle_events
        assert not service.is_initialized()
    
    @pytest.mark.asyncio
    async def test_multiple_service_types(self):
        """测试多种服务类型"""
        
        @repository("DataRepository")
        class DataRepository(BaseService):
            def get_data(self):
                return "repository_data"
        
        @service("BusinessService")
        class BusinessService(BaseService):
            @autowired("DataRepository")
            def data_repository(self):
                pass
                
            def process_data(self):
                return f"processed_{self.data_repository.get_data()}"
        
        container = ServiceContainer()
        
        # 手动注册服务
        from common.ioc.decorators import get_registered_services
        from common.ioc.base_service import ServiceMetadata
        from common.ioc.decorators import scan_dependencies
        
        registry = get_registered_services()
        for service_name, service_info in registry.items():
            dependencies = scan_dependencies(service_info['class'])
            metadata = ServiceMetadata(
                name=service_name,
                service_class=service_info['class'],
                service_type=service_info['type'],
                singleton=service_info['singleton'],
                dependencies=dependencies
            )
            container.register_service(metadata)
        
        await container.initialize()
        
        # 验证可以按类型获取服务
        repositories = container.get_services_by_type("repository")
        services = container.get_services_by_type("service")
        
        assert len(repositories) == 1
        assert len(services) == 1
        assert "DataRepository" in repositories
        assert "BusinessService" in services
        
        # 验证业务逻辑
        business_service = container.get_service("BusinessService")
        result = business_service.process_data()
        assert result == "processed_repository_data"
        
        await container.shutdown()
    
    def test_decorator_functionality(self):
        """测试装饰器功能"""
        
        @service("DecoratedService")
        class DecoratedService(BaseService):
            pass
        
        @repository("DecoratedRepository")
        class DecoratedRepository(BaseService):
            pass
        
        # 验证装饰器设置了正确的属性
        assert hasattr(DecoratedService, '_service_name')
        assert hasattr(DecoratedService, '_service_type')
        assert DecoratedService._service_name == "DecoratedService"
        assert DecoratedService._service_type == "service"
        
        assert hasattr(DecoratedRepository, '_service_name')
        assert hasattr(DecoratedRepository, '_service_type')
        assert DecoratedRepository._service_name == "DecoratedRepository"
        assert DecoratedRepository._service_type == "repository"


if __name__ == "__main__":
    pytest.main([__file__])