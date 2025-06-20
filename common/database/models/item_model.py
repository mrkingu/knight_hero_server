"""
道具数据模型
定义游戏道具的属性和类型
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from enum import IntEnum
from pydantic import BaseModel, Field

class ItemType(IntEnum):
    """道具类型枚举"""
    WEAPON = 1      # 武器
    ARMOR = 2       # 护甲
    ACCESSORY = 3   # 配饰
    CONSUMABLE = 4  # 消耗品
    MATERIAL = 5    # 材料
    CURRENCY = 6    # 货币

class ItemQuality(IntEnum):
    """道具品质枚举"""
    COMMON = 1      # 普通
    UNCOMMON = 2    # 不凡
    RARE = 3        # 稀有
    EPIC = 4        # 史诗
    LEGENDARY = 5   # 传说

class Item(BaseModel):
    """道具数据模型"""
    
    # 基础信息
    item_id: str = Field(..., description="道具ID")
    template_id: str = Field(..., description="道具模板ID")
    name: str = Field(..., description="道具名称")
    
    # 类型和品质
    item_type: ItemType = Field(..., description="道具类型")
    quality: ItemQuality = Field(default=ItemQuality.COMMON, description="道具品质")
    
    # 数量和堆叠
    quantity: int = Field(default=1, description="数量")
    max_stack: int = Field(default=1, description="最大堆叠数")
    
    # 属性
    level: int = Field(default=1, description="等级")
    durability: int = Field(default=100, description="耐久度")
    max_durability: int = Field(default=100, description="最大耐久度")
    
    # 增强
    enhance_level: int = Field(default=0, description="强化等级")
    gem_sockets: list = Field(default_factory=list, description="宝石槽位")
    
    # 绑定状态
    is_bound: bool = Field(default=False, description="是否绑定")
    bind_on_equip: bool = Field(default=False, description="装备绑定")
    
    # 时间相关
    expire_time: Optional[str] = Field(default=None, description="过期时间")
    
def get_concurrent_fields_item(model_class) -> Dict[str, Dict[str, Any]]:
    """
    获取道具支持并发操作的字段配置
    
    Args:
        model_class: 模型类
        
    Returns:
        并发字段配置字典
    """
    if model_class == Item:
        return {
            "quantity": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999
            },
            "durability": {
                "type": "number",
                "operations": ["decr"],
                "min": 0,
                "max": 999999
            }
        }
    return {}