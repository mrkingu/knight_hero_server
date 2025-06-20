"""
简单IoC测试 - 验证核心功能
Simple IoC Test to Verify Core Functionality

作者: mrkingu
日期: 2025-06-20
描述: 独立的测试，验证IoC框架的核心功能，不依赖现有的复杂基础设施
"""

import pytest
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.ioc import (
    service, repository, autowired, BaseService, ServiceContainer,
    ServiceScanner
)
from common.ioc.decorators import clear_registry
from common.ioc.base_service import ServiceMetadata
from common.ioc.decorators import get_registered_services, scan_dependencies


class TestSimpleIoC:
    """简单IoC测试"""
    
    def setup_method(self):
        """每个测试方法执行前清理注册表"""
        clear_registry()
    
    @pytest.mark.asyncio
    async def test_simple_dependency_injection(self):
        """测试简单的依赖注入"""
        
        # 在测试内部定义服务，避免pytest收集问题
        @repository("TestDataRepository")
        class TestDataRepository(BaseService):
            """测试数据仓库"""
            
            async def on_initialize(self):
                self.data = {"test": "repository_data"}
            
            def get_data(self):
                return self.data

        @service("TestBusinessService") 
        class TestBusinessService(BaseService):
            """测试业务服务"""
            
            @autowired("TestDataRepository")
            def data_repository(self):
                pass
            
            async def on_initialize(self):
                self.business_logic_ready = True
            
            def process_data(self):
                repo_data = self.data_repository.get_data()
                return f"processed_{repo_data['test']}"

        @service("TestHandler")
        class TestHandler(BaseService):
            """测试处理器"""
            
            @autowired("TestBusinessService")
            def business_service(self):
                pass
            
            async def handle_request(self, request):
                if not hasattr(self.business_service, 'business_logic_ready'):
                    return {"error": "Service not ready"}
                
                result = self.business_service.process_data()
                return {"success": True, "data": result}
        
        # 创建容器
        container = ServiceContainer()
        
        # 注册服务
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
        
        # 初始化容器
        await container.initialize()
        
        # 验证服务注册
        assert container.has_service("TestDataRepository")
        assert container.has_service("TestBusinessService")
        assert container.has_service("TestHandler")
        
        # 获取Handler并测试完整流程
        handler = container.get_service("TestHandler")
        
        # 验证依赖注入链
        assert hasattr(handler, 'business_service')
        business_service = handler.business_service
        assert business_service is not None
        
        assert hasattr(business_service, 'data_repository')
        data_repository = business_service.data_repository
        assert data_repository is not None
        
        # 测试业务逻辑
        result = await handler.handle_request({})
        assert result["success"] is True
        assert result["data"] == "processed_repository_data"
        
        # 清理
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """测试服务生命周期"""
        
        lifecycle_events = []
        
        from common.ioc import service  # 重新导入避免作用域问题
        
        @service("LifecycleTestService")
        class LifecycleTestService(BaseService):
            async def on_initialize(self):
                lifecycle_events.append("initialized")
            
            async def on_shutdown(self):
                lifecycle_events.append("shutdown")
        
        container = ServiceContainer()
        
        # 注册服务
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
        
        # 初始化
        await container.initialize()
        assert "initialized" in lifecycle_events
        
        # 获取服务
        service_instance = container.get_service("LifecycleTestService")
        assert service_instance.is_initialized()
        
        # 关闭
        await container.shutdown()
        assert "shutdown" in lifecycle_events
        assert not service_instance.is_initialized()
    
    @pytest.mark.asyncio
    async def test_initialization_order(self):
        """测试初始化顺序"""
        
        @repository("OrderTestRepository")
        class OrderTestRepository(BaseService):
            pass
        
        @service("OrderTestService") 
        class OrderTestService(BaseService):
            @autowired("OrderTestRepository")
            def repository(self):
                pass
        
        @service("OrderTestHandler")
        class OrderTestHandler(BaseService):
            @autowired("OrderTestService")
            def service(self):
                pass
        
        container = ServiceContainer()
        
        # 注册服务
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
        
        # 验证初始化顺序
        order = container._initialization_order
        
        repo_index = order.index("OrderTestRepository")
        service_index = order.index("OrderTestService") 
        handler_index = order.index("OrderTestHandler")
        
        # Repository -> Service -> Handler
        assert repo_index < service_index, f"Repository ({repo_index}) should come before Service ({service_index})"
        assert service_index < handler_index, f"Service ({service_index}) should come before Handler ({handler_index})"
        
        await container.shutdown()
    
    def test_decorator_registration(self):
        """测试装饰器注册功能"""
        
        @service("TestServiceA")
        class TestServiceA(BaseService):
            pass
        
        @repository("TestRepositoryA")
        class TestRepositoryA(BaseService):
            pass
        
        # 验证注册
        registry = get_registered_services()
        
        assert "TestServiceA" in registry
        assert registry["TestServiceA"]["type"] == "service"
        assert registry["TestServiceA"]["class"] == TestServiceA
        
        assert "TestRepositoryA" in registry
        assert registry["TestRepositoryA"]["type"] == "repository"
        assert registry["TestRepositoryA"]["class"] == TestRepositoryA


if __name__ == "__main__":
    pytest.main([__file__])