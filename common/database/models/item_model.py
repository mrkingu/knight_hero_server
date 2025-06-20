"""
道具数据模型
作者: mrkingu
日期: 2025-06-20
"""
from pydantic import Field
from typing import Dict, Any
from .base_document import BaseDocument

class ItemModel(BaseDocument):
    """道具数据模型"""
    
    item_id: int = Field(..., description="道具ID", index=True)
    name: str = Field(..., description="道具名称")
    type: int = Field(..., description="道具类型")
    quality: int = Field(default=1, description="品质")
    stack_limit: int = Field(default=999, description="堆叠上限")
    
    class Settings:
        name = "items"
        
    class Meta:
        cache_ttl = 3600  # 1小时