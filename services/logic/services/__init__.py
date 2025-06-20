"""
Logic服务业务逻辑模块
Logic Service Business Logic Module

作者: lx
日期: 2025-06-20
描述: 核心业务逻辑服务
"""

from .player_service import PlayerService

# Import IoC version
try:
    from .player_service_ioc import PlayerService as PlayerServiceIoC
    __all__ = [
        'PlayerService',
        'PlayerServiceIoC'
    ]
except ImportError:
    __all__ = [
        'PlayerService'
    ]