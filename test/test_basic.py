"""
测试模块
Test Module

作者: lx
日期: 2025-06-18
描述: 游戏服务器的单元测试和集成测试
"""

import pytest


def test_basic_import():
    """
    基础导入测试
    Basic import test
    """
    # 测试核心模块是否能正常导入
    try:
        import common
        import services
        import launcher
        assert True
    except ImportError as e:
        pytest.fail(f"模块导入失败: {e}")