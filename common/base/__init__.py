"""
基础架构模块
Base Architecture Module

作者: mrkingu
日期: 2025-06-20
描述: 提供统一的基础架构组件，包括BaseHandler、BaseGameService等
"""

from .base_handler import BaseHandler, DictHandler
from .base_game_service import BaseGameService

__all__ = [
    'BaseHandler',
    'DictHandler', 
    'BaseGameService'
]