"""
数据模型模块
统一导出所有数据模型
作者: lx
日期: 2025-06-20
"""
from .models.player_model import Player, VIPLevel, get_concurrent_fields
from .models.item_model import Item, ItemType, ItemQuality, get_concurrent_fields_item
from .models.guild_model import Guild, GuildPosition, GuildMember, get_concurrent_fields_guild
from .models.base_document import BaseDocument

__all__ = [
    'Player', 'VIPLevel', 'get_concurrent_fields',
    'Item', 'ItemType', 'ItemQuality', 'get_concurrent_fields_item',
    'Guild', 'GuildPosition', 'GuildMember', 'get_concurrent_fields_guild',
    'BaseDocument'
]