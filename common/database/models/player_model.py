"""
玩家数据模型
纯数据定义，不包含任何业务逻辑
作者: mrkingu
日期: 2025-06-20
"""
from pydantic import Field
from typing import Dict, List, Optional
from datetime import datetime
from .base_document import BaseDocument

class PlayerModel(BaseDocument):
    """玩家数据模型"""
    
    # 基础信息
    player_id: str = Field(..., description="玩家ID", index=True)
    account_id: str = Field(..., description="账号ID", index=True)
    nickname: str = Field(..., description="昵称")
    avatar: str = Field(default="", description="头像")
    
    # 等级信息
    level: int = Field(default=1, ge=1, le=100, description="等级")
    exp: int = Field(default=0, ge=0, description="经验值")
    vip_level: int = Field(default=0, ge=0, le=15, description="VIP等级")
    vip_exp: int = Field(default=0, ge=0, description="VIP经验")
    
    # 资源信息
    diamond: int = Field(default=0, ge=0, description="钻石")
    gold: int = Field(default=0, ge=0, description="金币")
    energy: int = Field(default=100, ge=0, le=999, description="体力")
    
    # 背包信息（简化存储）
    items: Dict[str, int] = Field(default_factory=dict, description="道具背包")
    
    # 时间信息
    last_login: datetime = Field(default_factory=datetime.utcnow, description="最后登录时间")
    last_offline: Optional[datetime] = Field(default=None, description="最后离线时间")
    
    class Settings:
        """MongoDB集合配置"""
        name = "players"
        
    class Meta:
        """元数据配置"""
        # 支持并发操作的字段
        concurrent_fields = {
            "diamond": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999
            },
            "gold": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999
            },
            "exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0,
                "max": 999999999
            },
            "energy": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999
            }
        }
        
        # 索引定义
        indexes = [
            "player_id",
            "account_id",
            [("level", -1), ("player_id", 1)],
            [("vip_level", -1), ("player_id", 1)]
        ]
        
        # 缓存配置
        cache_ttl = 300  # 5分钟