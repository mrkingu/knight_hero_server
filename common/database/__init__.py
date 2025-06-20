"""
数据库层模块
Database Layer Module

提供高性能、并发安全的数据访问层
作者: lx
日期: 2025-06-20
"""
from .core.redis_client import RedisClient
from .core.mongo_client import MongoClient
from .core.config import DatabaseConfig
from .concurrent.operation_type import OperationType
from .concurrent.atomic_operation import AtomicOperation
from .cache.cache_manager import CacheManager
from .repository.base_repository import BaseRepository
from .repositories.player_repository import PlayerRepository
from .models.player_model import Player
from .services.persistence_service import PersistenceService
from .utils.lua_scripts import LuaScripts

# 全局实例管理
_redis_client = None
_mongo_client = None
_operation_logger = None
_repository_manager = None

async def get_redis_cache():
    """获取Redis缓存客户端"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(DatabaseConfig.REDIS_CONFIG)
        await _redis_client.connect()
    return _redis_client

async def get_mongo_client():
    """获取MongoDB客户端"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(DatabaseConfig.MONGO_CONFIG)
        await _mongo_client.connect()
    return _mongo_client

async def get_operation_logger(mongo_client):
    """获取操作日志记录器"""
    global _operation_logger
    if _operation_logger is None:
        from .utils.logger import OperationLogger
        _operation_logger = OperationLogger(mongo_client)
    return _operation_logger

async def get_repository_manager(redis_client, mongo_client):
    """获取仓库管理器"""
    global _repository_manager
    if _repository_manager is None:
        from .repository.repository_manager import RepositoryManager
        _repository_manager = RepositoryManager(redis_client, mongo_client)
    return _repository_manager

async def close_redis_cache():
    """关闭Redis连接"""
    global _redis_client
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None

async def close_mongo_client():
    """关闭MongoDB连接"""
    global _mongo_client
    if _mongo_client:
        await _mongo_client.disconnect()
        _mongo_client = None

async def close_operation_logger():
    """关闭操作日志"""
    global _operation_logger
    _operation_logger = None

async def close_repository_manager():
    """关闭仓库管理器"""
    global _repository_manager
    _repository_manager = None

__all__ = [
    'RedisClient',
    'MongoClient', 
    'DatabaseConfig',
    'OperationType',
    'AtomicOperation',
    'CacheManager',
    'BaseRepository',
    'PlayerRepository',
    'Player',
    'PersistenceService',
    'LuaScripts',
    'get_redis_cache',
    'get_mongo_client',
    'get_operation_logger', 
    'get_repository_manager',
    'close_redis_cache',
    'close_mongo_client',
    'close_operation_logger',
    'close_repository_manager'
]