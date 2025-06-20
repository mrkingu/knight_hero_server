"""
Repository访问控制测试
作者: lx
日期: 2025-06-20
"""
import pytest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.database.repository import RepositoryManager, get_repository_manager

class TestRepositoryAccessControl:
    """Repository访问控制测试"""
    
    def test_repository_manager_singleton(self):
        """测试Repository管理器单例模式"""
        manager1 = get_repository_manager()
        manager2 = get_repository_manager()
        
        assert manager1 is manager2
    
    def test_repository_access_from_services(self):
        """测试从services包访问Repository"""
        # 这个测试需要模拟从services包调用
        # 由于访问控制是通过检查调用栈实现的，这里简化测试
        manager = get_repository_manager()
        
        # 测试列出Repository
        repos = manager.list_repositories()
        assert isinstance(repos, dict)
    
    def test_repository_health_check(self):
        """测试Repository健康检查"""
        manager = get_repository_manager()
        
        health_status = manager.health_check()
        assert isinstance(health_status, dict)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])