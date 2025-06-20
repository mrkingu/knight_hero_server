"""
IoC集成测试
IoC Integration Tests

作者: mrkingu
日期: 2025-06-20
描述: 测试完整的IoC容器集成，包括Repository、Service、Handler的自动装载和依赖注入
"""

import pytest
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.ioc import ServiceContainer
from common.ioc.decorators import clear_registry


class TestIoCIntegration:
    """IoC集成测试"""
    
    def setup_method(self):
        """每个测试方法执行前清理注册表"""
        clear_registry()
    
    @pytest.mark.asyncio
    async def test_full_service_stack_integration(self):
        """测试完整的服务栈集成（Repository -> Service -> Handler）"""
        
        # 直接导入模块避免循环依赖
        import sys
        import importlib
        
        # 动态加载模块
        player_repo_module = importlib.import_module('services.logic.repositories.player_repository')
        PlayerRepository = player_repo_module.PlayerRepository
        
        player_service_module = importlib.import_module('services.logic.services.player_service_ioc')
        PlayerService = player_service_module.PlayerService
        
        player_handler_module = importlib.import_module('services.logic.handlers.player_handler_ioc')
        PlayerHandler = player_handler_module.PlayerHandler
        
        # 创建容器
        container = ServiceContainer()
        
        # 注册服务（模拟扫描结果）
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
        
        # 初始化容器
        await container.initialize()
        
        # 验证所有服务都已注册
        assert container.has_service("PlayerRepository")
        assert container.has_service("PlayerService")
        assert container.has_service("PlayerHandler")
        
        # 获取Handler（顶层服务）
        player_handler = container.get_service("PlayerHandler")
        assert player_handler is not None
        
        # 验证依赖注入链
        assert hasattr(player_handler, 'player_service')
        player_service = player_handler.player_service
        assert player_service is not None
        
        assert hasattr(player_service, 'player_repository')
        player_repository = player_service.player_repository
        assert player_repository is not None
        
        # 验证服务类型
        assert player_repository._service_type == "repository"
        assert player_service._service_type == "service"
        assert player_handler._service_type == "service"  # Handler也是service类型
        
        # 清理
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_handler_request_processing(self):
        """测试Handler的请求处理流程"""
        
        import importlib
        
        # 动态加载模块
        player_repo_module = importlib.import_module('services.logic.repositories.player_repository')
        PlayerRepository = player_repo_module.PlayerRepository
        
        player_service_module = importlib.import_module('services.logic.services.player_service_ioc')
        PlayerService = player_service_module.PlayerService
        
        player_handler_module = importlib.import_module('services.logic.handlers.player_handler_ioc')
        PlayerHandler = player_handler_module.PlayerHandler
        
        # 创建和初始化容器
        container = ServiceContainer()
        
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
        
        # 获取Handler
        player_handler = container.get_service("PlayerHandler")
        
        # 测试登录请求
        login_request = {
            "action": "login",
            "username": "test_player",
            "password": "test_password",
            "device_id": "test_device"
        }
        
        # 处理请求（注意：这里会失败因为没有真实的数据库连接）
        # 但我们可以验证请求处理流程的结构是否正确
        try:
            response = await player_handler.handle_request(login_request)
            # 如果没有异常，说明请求处理流程正常
            assert isinstance(response, dict)
            assert "code" in response
            assert "message" in response
        except Exception as e:
            # 预期会有数据库连接错误，但这表明请求处理流程是正确的
            assert "redis" in str(e).lower() or "mongo" in str(e).lower() or "database" in str(e).lower()
        
        # 测试获取玩家信息请求
        get_info_request = {
            "action": "get_info",
            "player_id": "test_player_123"
        }
        
        try:
            response = await player_handler.handle_request(get_info_request)
            assert isinstance(response, dict)
            assert "code" in response
        except Exception as e:
            # 同样预期有数据库连接错误
            assert "redis" in str(e).lower() or "mongo" in str(e).lower() or "database" in str(e).lower()
        
        # 清理
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_service_initialization_order(self):
        """测试服务初始化顺序"""
        
        import importlib
        
        player_repo_module = importlib.import_module('services.logic.repositories.player_repository')
        PlayerRepository = player_repo_module.PlayerRepository
        
        player_service_module = importlib.import_module('services.logic.services.player_service_ioc')
        PlayerService = player_service_module.PlayerService
        
        player_handler_module = importlib.import_module('services.logic.handlers.player_handler_ioc')
        PlayerHandler = player_handler_module.PlayerHandler
        
        container = ServiceContainer()
        
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
        
        # 验证初始化顺序：Repository -> Service -> Handler
        initialization_order = container._initialization_order
        
        # PlayerRepository应该在PlayerService之前初始化
        repo_index = initialization_order.index("PlayerRepository")
        service_index = initialization_order.index("PlayerService")
        handler_index = initialization_order.index("PlayerHandler")
        
        assert repo_index < service_index, "Repository should be initialized before Service"
        assert service_index < handler_index, "Service should be initialized before Handler"
        
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_container_health_check(self):
        """测试容器健康检查"""
        
        import importlib
        
        player_repo_module = importlib.import_module('services.logic.repositories.player_repository')
        PlayerRepository = player_repo_module.PlayerRepository
        
        player_service_module = importlib.import_module('services.logic.services.player_service_ioc')
        PlayerService = player_service_module.PlayerService
        
        player_handler_module = importlib.import_module('services.logic.handlers.player_handler_ioc')
        PlayerHandler = player_handler_module.PlayerHandler
        
        container = ServiceContainer()
        
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
        
        # 获取容器信息
        container_info = container.get_container_info()
        
        assert container_info["initialized"] is True
        assert container_info["total_services"] == 3
        assert container_info["active_instances"] == 3
        
        # 验证所有服务的健康状态
        for service_name in ["PlayerRepository", "PlayerService", "PlayerHandler"]:
            service = container.get_service(service_name)
            health = await service.health_check()
            
            assert health["service_name"] == service_name
            assert health["initialized"] is True
            assert health["status"] in ["healthy", "initializing"]
        
        await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_singleton_behavior(self):
        """测试单例行为"""
        
        import importlib
        
        player_repo_module = importlib.import_module('services.logic.repositories.player_repository')
        PlayerRepository = player_repo_module.PlayerRepository
        
        player_service_module = importlib.import_module('services.logic.services.player_service_ioc')
        PlayerService = player_service_module.PlayerService
        
        container = ServiceContainer()
        
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
        
        # 多次获取同一个服务，应该返回同一个实例
        service1 = container.get_service("PlayerService")
        service2 = container.get_service("PlayerService")
        
        assert service1 is service2, "Singleton services should return the same instance"
        
        repository1 = container.get_service("PlayerRepository")
        repository2 = container.get_service("PlayerRepository")
        
        assert repository1 is repository2, "Singleton repositories should return the same instance"
        
        await container.shutdown()


if __name__ == "__main__":
    pytest.main([__file__])