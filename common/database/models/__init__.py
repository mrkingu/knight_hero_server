"""
数据模型模块
作者: mrkingu
日期: 2025-06-20
"""
from .base_document import BaseDocument
from .player_model import PlayerModel
from .guild_model import GuildModel
from .item_model import ItemModel

__all__ = ['BaseDocument', 'PlayerModel', 'GuildModel', 'ItemModel']