"""
日志模块
Logger Module

作者: lx
日期: 2025-06-18
描述: 统一日志管理和输出格式化
"""

import asyncio
import os
from typing import Dict, Any, Optional

from .async_logger import AsyncLogger, AsyncLoggerManager, _logger_manager
from .config import get_config
from .formatters import JSONFormatter, SimpleFormatter, ColoredFormatter
from .handlers import (
    AsyncFileHandler, 
    AsyncRotatingFileHandler, 
    AsyncTimedRotatingFileHandler,
    AsyncConsoleHandler
)

# 全局日志器实例缓存
_loggers: Dict[str, AsyncLogger] = {}
_initialized = False


async def initialize_loggers(environment: str = "production") -> None:
    """
    初始化日志系统
    
    Args:
        environment: 环境名称 ("production", "development")
    """
    global _initialized
    if _initialized:
        return
    
    config = get_config(environment)
    
    # 配置所有日志器
    for logger_name, logger_config in config.items():
        logger = await _logger_manager.configure_logger(logger_name, logger_config)
        _loggers[logger_name] = logger
    
    _initialized = True


async def get_logger(name: str) -> AsyncLogger:
    """
    获取日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        异步日志器实例
    """
    if not _initialized:
        await initialize_loggers()
    
    if name in _loggers:
        return _loggers[name]
    
    # 如果不存在，创建默认配置的日志器
    logger = await _logger_manager.get_logger(name)
    _loggers[name] = logger
    return logger


async def shutdown_loggers() -> None:
    """关闭所有日志器"""
    global _initialized
    if not _initialized:
        return
    
    await _logger_manager.stop_all()
    _loggers.clear()
    _initialized = False


# 预配置的日志器实例 - 延迟初始化
_player_logger: Optional[AsyncLogger] = None
_battle_logger: Optional[AsyncLogger] = None
_system_logger: Optional[AsyncLogger] = None
_error_logger: Optional[AsyncLogger] = None
_debug_logger: Optional[AsyncLogger] = None


async def get_player_logger() -> AsyncLogger:
    """获取玩家日志器"""
    global _player_logger
    if _player_logger is None:
        _player_logger = await get_logger("player")
    return _player_logger


async def get_battle_logger() -> AsyncLogger:
    """获取战斗日志器"""
    global _battle_logger
    if _battle_logger is None:
        _battle_logger = await get_logger("battle")
    return _battle_logger


async def get_system_logger() -> AsyncLogger:
    """获取系统日志器"""
    global _system_logger
    if _system_logger is None:
        _system_logger = await get_logger("system")
    return _system_logger


async def get_error_logger() -> AsyncLogger:
    """获取错误日志器"""
    global _error_logger
    if _error_logger is None:
        _error_logger = await get_logger("error")
    return _error_logger


async def get_debug_logger() -> AsyncLogger:
    """获取调试日志器"""
    global _debug_logger
    if _debug_logger is None:
        _debug_logger = await get_logger("debug")
    return _debug_logger


# 便捷的日志记录函数
async def log_player_action(
    action: str, 
    player_id: str, 
    **extra_data: Any
) -> bool:
    """
    记录玩家操作日志
    
    Args:
        action: 操作描述
        player_id: 玩家ID
        **extra_data: 额外数据
        
    Returns:
        是否成功记录
    """
    logger = await get_player_logger()
    return await logger.info(
        action,
        player_id=player_id,
        **extra_data
    )


async def log_battle_event(
    event: str,
    battle_id: str,
    **extra_data: Any
) -> bool:
    """
    记录战斗事件日志
    
    Args:
        event: 事件描述
        battle_id: 战斗ID
        **extra_data: 额外数据
        
    Returns:
        是否成功记录
    """
    logger = await get_battle_logger()
    return await logger.info(
        event,
        battle_id=battle_id,
        **extra_data
    )


async def log_system_event(
    event: str,
    component: str,
    **extra_data: Any
) -> bool:
    """
    记录系统事件日志
    
    Args:
        event: 事件描述
        component: 组件名称
        **extra_data: 额外数据
        
    Returns:
        是否成功记录
    """
    logger = await get_system_logger()
    return await logger.info(
        event,
        component=component,
        **extra_data
    )


async def log_error(
    error: str,
    error_type: str = "Unknown",
    trace_id: Optional[str] = None,
    **extra_data: Any
) -> bool:
    """
    记录错误日志
    
    Args:
        error: 错误描述
        error_type: 错误类型
        trace_id: 追踪ID
        **extra_data: 额外数据
        
    Returns:
        是否成功记录
    """
    logger = await get_error_logger()
    return await logger.error(
        error,
        error_type=error_type,
        trace_id=trace_id,
        **extra_data
    )


def get_logger_stats() -> Dict[str, Dict[str, Any]]:
    """获取所有日志器的统计信息"""
    return _logger_manager.get_all_stats()


# 为了向后兼容，提供同步版本的便捷函数
def create_logger_task(coro):
    """创建日志任务的辅助函数"""
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)
    except RuntimeError:
        # 如果没有运行的事件循环，尝试在新线程中运行
        return asyncio.create_task(coro)


# 同步包装函数
def sync_log_player_action(action: str, player_id: str, **extra_data: Any):
    """同步版本的玩家操作日志"""
    return create_logger_task(log_player_action(action, player_id, **extra_data))


def sync_log_battle_event(event: str, battle_id: str, **extra_data: Any):
    """同步版本的战斗事件日志"""
    return create_logger_task(log_battle_event(event, battle_id, **extra_data))


def sync_log_system_event(event: str, component: str, **extra_data: Any):
    """同步版本的系统事件日志"""
    return create_logger_task(log_system_event(event, component, **extra_data))


def sync_log_error(error: str, error_type: str = "Unknown", **extra_data: Any):
    """同步版本的错误日志"""
    return create_logger_task(log_error(error, error_type, **extra_data))


# 导出所有公共接口
__all__ = [
    # 核心类
    "AsyncLogger",
    "AsyncLoggerManager", 
    
    # 格式化器
    "JSONFormatter",
    "SimpleFormatter", 
    "ColoredFormatter",
    
    # 处理器
    "AsyncFileHandler",
    "AsyncRotatingFileHandler", 
    "AsyncTimedRotatingFileHandler",
    "AsyncConsoleHandler",
    
    # 初始化和管理
    "initialize_loggers",
    "get_logger",
    "shutdown_loggers",
    
    # 预配置日志器
    "get_player_logger",
    "get_battle_logger", 
    "get_system_logger",
    "get_error_logger",
    "get_debug_logger",
    
    # 便捷日志函数
    "log_player_action",
    "log_battle_event",
    "log_system_event", 
    "log_error",
    
    # 同步包装函数
    "sync_log_player_action",
    "sync_log_battle_event",
    "sync_log_system_event",
    "sync_log_error",
    
    # 统计
    "get_logger_stats"
]