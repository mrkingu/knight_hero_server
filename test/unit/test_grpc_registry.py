"""
gRPC服务注册中心测试
作者: lx
日期: 2025-06-20
"""
import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.grpc.service_registry import ServiceRegistry, ServiceType, get_service_registry

class TestServiceRegistry:
    """服务注册中心测试"""
    
    def test_service_registry_creation(self):
        """测试服务注册中心创建"""
        registry = ServiceRegistry()
        assert registry is not None
    
    def test_get_service_addresses(self):
        """测试获取服务地址"""
        registry = ServiceRegistry()
        
        # 测试获取LOGIC服务地址
        addresses = registry.get_service_addresses(ServiceType.LOGIC)
        assert isinstance(addresses, list)
        assert len(addresses) >= 0  # 可能为空，但应该是列表
    
    def test_register_service(self):
        """测试注册服务"""
        registry = ServiceRegistry()
        
        # 注册新服务
        registry.register_service(ServiceType.LOGIC, "localhost", 9999)
        
        # 检查是否注册成功
        addresses = registry.get_service_addresses(ServiceType.LOGIC)
        assert ("localhost", 9999) in addresses
    
    def test_unregister_service(self):
        """测试注销服务"""
        registry = ServiceRegistry()
        
        # 先注册
        registry.register_service(ServiceType.LOGIC, "localhost", 9999)
        
        # 再注销
        registry.unregister_service(ServiceType.LOGIC, "localhost", 9999)
        
        # 检查是否注销成功
        addresses = registry.get_service_addresses(ServiceType.LOGIC)
        assert ("localhost", 9999) not in addresses
    
    def test_get_random_address(self):
        """测试随机获取地址"""
        registry = ServiceRegistry()
        
        # 注册几个服务
        registry.register_service(ServiceType.LOGIC, "localhost", 9001)
        registry.register_service(ServiceType.LOGIC, "localhost", 9002)
        
        # 获取随机地址
        address = registry.get_random_address(ServiceType.LOGIC)
        assert address in [("localhost", 9001), ("localhost", 9002)]
    
    def test_service_count(self):
        """测试获取服务数量"""
        registry = ServiceRegistry()
        
        # 注册服务
        registry.register_service(ServiceType.CHAT, "localhost", 9101)
        registry.register_service(ServiceType.CHAT, "localhost", 9102)
        
        # 检查数量
        count = registry.get_service_count(ServiceType.CHAT)
        assert count >= 2
    
    def test_health_check(self):
        """测试健康检查"""
        registry = ServiceRegistry()
        
        # 注册服务
        registry.register_service(ServiceType.FIGHT, "localhost", 9201)
        
        # 健康检查
        health_status = registry.health_check(ServiceType.FIGHT)
        assert isinstance(health_status, dict)
        assert ("localhost", 9201) in health_status
    
    def test_global_registry(self):
        """测试全局注册中心"""
        registry1 = get_service_registry()
        registry2 = get_service_registry()
        
        # 应该是同一个实例
        assert registry1 is registry2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])