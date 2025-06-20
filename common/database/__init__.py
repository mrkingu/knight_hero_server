"""
数据库模块
Database Module

作者: lx
日期: 2025-06-18
描述: 数据库连接、模型定义和数据访问层

本模块实现了高性能的数据访问层，包括：
- Redis缓存层：高性能缓存、布隆过滤器、分布式锁
- MongoDB持久化：异步操作、批量写入优化
- Repository模式：自动并发控制、事务管理
- 操作日志：完整审计跟踪、回滚支持
- 数据持久化：异步同步、一致性检查

核心特性：
1. 自动并发控制 - 业务层无需关心并发问题
2. 高性能缓存 - Redis < 1ms, 缓存命中率 > 95%
3. 批量操作优化 - MongoDB > 10K/s 写入性能
4. 完整审计日志 - 所有操作可追踪、可回滚
5. 自动幂等性 - 支付、定时任务等场景防重复处理
"""

# 导出核心类和函数
from .redis_cache import RedisCache, get_redis_cache, close_redis_cache
from .mongo_client import MongoClient, get_mongo_client, close_mongo_client
from .operation_logger import OperationLogger, get_operation_logger, close_operation_logger
from .persistence_service import PersistenceService, get_persistence_service, close_persistence_service
from .base_repository import BaseRepository
from .repository_gen import RepositoryManager, get_repository_manager, close_repository_manager
from .repositories.player_repository import PlayerRepository
from .models import Player, Guild, GameConfig, OperationLog, PaymentOrder, ScheduledTask, RewardRecord, ALL_DOCUMENT_MODELS
from .concurrent_operations import OperationType, ConcurrentOperation, OperationResult
from .distributed_lock import DistributedLock, distributed_lock, reentrant_lock

__all__ = [
    # 核心客户端
    "RedisCache",
    "MongoClient", 
    "OperationLogger",
    "PersistenceService",
    
    # Repository相关
    "BaseRepository",
    "RepositoryManager",
    "PlayerRepository",
    
    # 数据模型
    "Player",
    "Guild", 
    "GameConfig",
    "OperationLog",
    "PaymentOrder",
    "ScheduledTask", 
    "RewardRecord",
    "ALL_DOCUMENT_MODELS",
    
    # 并发控制
    "OperationType",
    "ConcurrentOperation",
    "OperationResult",
    "DistributedLock",
    "distributed_lock",
    "reentrant_lock",
    
    # 工厂函数
    "get_redis_cache",
    "get_mongo_client",
    "get_operation_logger",
    "get_persistence_service",
    "get_repository_manager",
    
    # 关闭函数
    "close_redis_cache",
    "close_mongo_client", 
    "close_operation_logger",
    "close_persistence_service",
    "close_repository_manager",
]

# 版本信息
__version__ = "1.0.0"
__author__ = "lx"
__description__ = "高性能游戏数据库层 - 自动并发控制、缓存优化、完整审计"