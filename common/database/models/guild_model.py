"""
公会数据模型
作者: mrkingu
日期: 2025-06-20
"""
from pydantic import Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from .base_document import BaseDocument

class GuildModel(BaseDocument):
    """公会数据模型"""
    
    guild_id: str = Field(..., description="公会ID", index=True)
    name: str = Field(..., description="公会名称", index=True)
    level: int = Field(default=1, description="公会等级")
    exp: int = Field(default=0, description="公会经验")
    members: List[str] = Field(default_factory=list, description="成员列表")
    
    class Settings:
        name = "guilds"
        
    class Meta:
        concurrent_fields = {
            "exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0
            }
        }