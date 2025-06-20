"""
玩家数据模型
定义玩家的所有属性和并发字段
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from enum import IntEnum
from pydantic import BaseModel, Field
from .base_document import BaseDocument

class VIPLevel(IntEnum):
    """VIP等级枚举"""
    V0 = 0
    V1 = 1
    V2 = 2
    V3 = 3
    V4 = 4
    V5 = 5
    V6 = 6
    V7 = 7
    V8 = 8
    V9 = 9
    V10 = 10

class Player(BaseDocument):
    """玩家数据模型"""
    
    # 基础信息
    player_id: str = Field(..., description="玩家ID")
    nickname: str = Field(..., description="昵称")
    level: int = Field(default=1, description="等级")
    exp: int = Field(default=0, description="经验值")
    
    # 货币资源（支持并发操作的字段）
    diamond: int = Field(default=0, description="钻石")
    gold: int = Field(default=0, description="金币")
    energy: int = Field(default=100, description="体力")
    
    # VIP信息
    vip_level: VIPLevel = Field(default=VIPLevel.V0, description="VIP等级")
    vip_exp: int = Field(default=0, description="VIP经验")
    
    # 状态信息
    last_login: Optional[str] = Field(default=None, description="最后登录时间")
    online_status: bool = Field(default=False, description="在线状态")
    
    class Settings:
        collection = "players"

def get_concurrent_fields(model_class) -> Dict[str, Dict[str, Any]]:
    """
    获取支持并发操作的字段配置
    
    Args:
        model_class: 模型类
        
    Returns:
        并发字段配置字典
    """
    if model_class == Player:
        return {
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
    return {}