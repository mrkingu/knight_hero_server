"""
数据库模块
作者: mrkingu  
日期: 2025-06-20
"""
# 核心组件
from .core.redis_client import RedisClient
from .core.mongo_client import MongoClient

# 仓库相关
from .repository.base_repository import BaseRepository

# 当前仓库（向后兼容）
from .repositories.player_repository import PlayerRepository
from .repositories.guild_repository import GuildRepository  
from .repositories.item_repository import ItemRepository

# 模型
from .models.player_model import PlayerModel
from .models.guild_model import GuildModel
from .models.item_model import ItemModel

# 并发控制
from .concurrent.operation_type import OperationType
from .concurrent.atomic_operation import AtomicOperation

__all__ = [
    'RedisClient', 'MongoClient',
    'BaseRepository',
    'PlayerRepository', 'GuildRepository', 'ItemRepository',
    'PlayerModel', 'GuildModel', 'ItemModel',
    'OperationType', 'AtomicOperation'
]