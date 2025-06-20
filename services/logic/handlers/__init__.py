"""
Logic服务处理器模块
Logic Service Handlers Module

作者: lx
日期: 2025-06-20
描述: 处理客户端请求的业务逻辑
"""

from .base_handler import BaseHandler, handler, register_handler_class
from .player_handler import PlayerHandler

# Import IoC version
try:
    from .player_handler_ioc import PlayerHandler as PlayerHandlerIoC
    __all__ = [
        'BaseHandler',
        'handler', 
        'register_handler_class',
        'PlayerHandler',
        'PlayerHandlerIoC'
    ]
except ImportError:
    __all__ = [
        'BaseHandler',
        'handler', 
        'register_handler_class',
        'PlayerHandler'
    ]