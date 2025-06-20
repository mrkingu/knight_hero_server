"""
自动生成的配置类文件
Auto-generated Configuration Classes

作者: lx (自动生成)
日期: 2025-06-20
描述: 根据JSON配置文件自动生成的Pydantic配置类
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Union
from common.config.base_config import BaseConfig

# 自动生成的配置类

class ItemConfig(BaseConfig):
    """Item配置"""

    item_id: int = Field(description="ID")
    name: str = Field(description="名称")
    type: int = Field(description="类型")
    quality: int = Field(description="品质")
    price: int = Field(description="价格")
    description: str = Field(description="描述")
    max_stack: int = Field(description="最大堆叠")
    level_requirement: int = Field(description="等级")

class NpcConfig(BaseConfig):
    """Npc配置"""

    npc_id: int = Field(description="ID")
    name: str = Field(description="名称")
    level: int = Field(description="等级")
    hp: int = Field(description="生命值")
    attack: int = Field(description="攻击力")
    defense: int = Field(description="防御力")
    drop_items: List[Any] = Field(default_factory=list, description="掉落道具")
    ai_type: int = Field(description="类型")

class SkillConfig(BaseConfig):
    """Skill配置"""

    skill_id: int = Field(description="ID")
    name: str = Field(description="名称")
    type: int = Field(description="类型")
    level: int = Field(description="等级")
    damage: int = Field(description="伤害")
    mana_cost: int = Field(description="魔法消耗")
    cooldown: float = Field(description="冷却时间")
    description: str = Field(description="描述")

class GeneratedConfigManager:
    """自动生成的配置管理器"""

    def __init__(self):
        """初始化配置管理器"""
        self.item_config: Dict[int, ItemConfig] = {}
        self.npc_config: Dict[int, NpcConfig] = {}
        self.skill_config: Dict[int, SkillConfig] = {}

    # 配置获取方法
    def get_item(self, config_id: int) -> Optional[ItemConfig]:
        """获取Item配置"""
        return self.item_config.get(config_id)

    def get_npc(self, config_id: int) -> Optional[NpcConfig]:
        """获取Npc配置"""
        return self.npc_config.get(config_id)

    def get_skill(self, config_id: int) -> Optional[SkillConfig]:
        """获取Skill配置"""
        return self.skill_config.get(config_id)

    def clear_all(self):
        """清空所有配置"""
        self.item_config.clear()
        self.npc_config.clear()
        self.skill_config.clear()


# 全局配置管理器实例
generated_config_manager = GeneratedConfigManager()

def get_generated_config_manager() -> GeneratedConfigManager:
    """获取自动生成的配置管理器实例"""
    return generated_config_manager