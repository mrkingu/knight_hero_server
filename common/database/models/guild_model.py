"""
公会数据模型
定义公会的属性和成员管理
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, List, Optional
from enum import IntEnum
from pydantic import BaseModel, Field

class GuildPosition(IntEnum):
    """公会职位枚举"""
    MEMBER = 1      # 成员
    OFFICER = 2     # 官员
    DEPUTY = 3      # 副会长
    LEADER = 4      # 会长

class GuildMember(BaseModel):
    """公会成员模型"""
    player_id: str = Field(..., description="玩家ID")
    nickname: str = Field(..., description="昵称")
    position: GuildPosition = Field(default=GuildPosition.MEMBER, description="职位")
    join_time: str = Field(..., description="加入时间")
    contribution: int = Field(default=0, description="贡献度")
    last_active: Optional[str] = Field(default=None, description="最后活跃时间")

class Guild(BaseModel):
    """公会数据模型"""
    
    # 基础信息
    guild_id: str = Field(..., description="公会ID")
    name: str = Field(..., description="公会名称")
    tag: str = Field(..., description="公会标签")
    
    # 公会状态
    level: int = Field(default=1, description="公会等级")
    exp: int = Field(default=0, description="公会经验")
    funds: int = Field(default=0, description="公会资金")
    
    # 成员管理
    members: List[GuildMember] = Field(default_factory=list, description="成员列表")
    max_members: int = Field(default=30, description="最大成员数")
    
    # 公会设置
    description: str = Field(default="", description="公会描述")
    notice: str = Field(default="", description="公会公告")
    join_condition: str = Field(default="auto", description="加入条件")
    
    # 活动相关
    activity_points: int = Field(default=0, description="活动积分")
    
    # 创建信息
    created_time: str = Field(..., description="创建时间")
    leader_id: str = Field(..., description="会长ID")

def get_concurrent_fields_guild(model_class) -> Dict[str, Dict[str, Any]]:
    """
    获取公会支持并发操作的字段配置
    
    Args:
        model_class: 模型类
        
    Returns:
        并发字段配置字典
    """
    if model_class == Guild:
        return {
            "exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0,
                "max": 999999999
            },
            "funds": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999
            },
            "activity_points": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999
            }
        }
    return {}