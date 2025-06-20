"""
配置基类模块
Configuration Base Classes Module

作者: lx
日期: 2025-06-18
描述: 配置系统的基础类和配置管理器
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Any, Optional
from datetime import datetime


class BaseConfig(BaseModel):
    """配置基类"""
    
    model_config = ConfigDict(
        # 禁止额外字段
        extra="forbid",
        # 使用枚举值
        use_enum_values=True,
        # 允许属性验证
        validate_assignment=True
    )


class ItemConfig(BaseConfig):
    """道具配置"""
    item_id: int = Field(description="道具ID")
    name: str = Field(description="道具名称")
    type: int = Field(description="道具类型")
    quality: int = Field(description="道具品质", ge=1, le=5)
    price: int = Field(description="道具价格", ge=0)
    description: str = Field(description="道具描述")
    max_stack: int = Field(default=1, description="最大堆叠数量", ge=1)
    level_requirement: int = Field(default=1, description="等级需求", ge=1)


class SkillConfig(BaseConfig):
    """技能配置"""
    skill_id: int = Field(description="技能ID")
    name: str = Field(description="技能名称")
    type: int = Field(description="技能类型")
    level: int = Field(description="技能等级", ge=1)
    damage: int = Field(description="伤害值", ge=0)
    mana_cost: int = Field(description="魔法消耗", ge=0)
    cooldown: float = Field(description="冷却时间(秒)", ge=0)
    description: str = Field(description="技能描述")


class NpcConfig(BaseConfig):
    """NPC配置"""
    npc_id: int = Field(description="NPC ID")
    name: str = Field(description="NPC名称")
    level: int = Field(description="NPC等级", ge=1)
    hp: int = Field(description="生命值", ge=1)
    attack: int = Field(description="攻击力", ge=0)
    defense: int = Field(description="防御力", ge=0)
    drop_items: List[int] = Field(default_factory=list, description="掉落道具列表")
    ai_type: str = Field(description="AI类型")


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.item_config: Dict[int, ItemConfig] = {}
        self.skill_config: Dict[int, SkillConfig] = {}
        self.npc_config: Dict[int, NpcConfig] = {}
        
        # 配置加载时间戳，用于热更新检测
        self._load_timestamp: Optional[datetime] = None
        self._config_files: Dict[str, float] = {}  # 文件路径 -> 修改时间
        
    def get_item(self, item_id: int) -> Optional[ItemConfig]:
        """获取道具配置
        
        Args:
            item_id: 道具ID
            
        Returns:
            道具配置对象，如果不存在返回None
        """
        return self.item_config.get(item_id)
        
    def get_skill(self, skill_id: int) -> Optional[SkillConfig]:
        """获取技能配置
        
        Args:
            skill_id: 技能ID
            
        Returns:
            技能配置对象，如果不存在返回None
        """
        return self.skill_config.get(skill_id)
        
    def get_npc(self, npc_id: int) -> Optional[NpcConfig]:
        """获取NPC配置
        
        Args:
            npc_id: NPC ID
            
        Returns:
            NPC配置对象，如果不存在返回None
        """
        return self.npc_config.get(npc_id)
        
    def get_all_items(self) -> Dict[int, ItemConfig]:
        """获取所有道具配置"""
        return self.item_config.copy()
        
    def get_all_skills(self) -> Dict[int, SkillConfig]:
        """获取所有技能配置"""
        return self.skill_config.copy()
        
    def get_all_npcs(self) -> Dict[int, NpcConfig]:
        """获取所有NPC配置"""
        return self.npc_config.copy()
        
    def get_items_by_type(self, item_type: int) -> List[ItemConfig]:
        """根据类型获取道具配置
        
        Args:
            item_type: 道具类型
            
        Returns:
            符合类型的道具配置列表
        """
        return [item for item in self.item_config.values() if item.type == item_type]
        
    def get_skills_by_type(self, skill_type: int) -> List[SkillConfig]:
        """根据类型获取技能配置
        
        Args:
            skill_type: 技能类型
            
        Returns:
            符合类型的技能配置列表
        """
        return [skill for skill in self.skill_config.values() if skill.type == skill_type]
        
    def clear_all(self):
        """清空所有配置"""
        self.item_config.clear()
        self.skill_config.clear()
        self.npc_config.clear()
        self._load_timestamp = None
        self._config_files.clear()
        
    def get_config_count(self) -> Dict[str, int]:
        """获取配置数量统计
        
        Returns:
            各类配置的数量统计
        """
        return {
            "items": len(self.item_config),
            "skills": len(self.skill_config),
            "npcs": len(self.npc_config),
            "total": len(self.item_config) + len(self.skill_config) + len(self.npc_config)
        }
        
    def validate_all_configs(self) -> Dict[str, List[str]]:
        """验证所有配置的完整性
        
        Returns:
            验证错误信息，按配置类型分组
        """
        errors = {
            "items": [],
            "skills": [],
            "npcs": []
        }
        
        # 验证道具配置
        for item_id, item in self.item_config.items():
            try:
                # 重新验证配置对象
                ItemConfig.model_validate(item.model_dump())
            except Exception as e:
                errors["items"].append(f"道具ID {item_id}: {str(e)}")
                
        # 验证技能配置
        for skill_id, skill in self.skill_config.items():
            try:
                SkillConfig.model_validate(skill.model_dump())
            except Exception as e:
                errors["skills"].append(f"技能ID {skill_id}: {str(e)}")
                
        # 验证NPC配置
        for npc_id, npc in self.npc_config.items():
            try:
                NpcConfig.model_validate(npc.model_dump())
            except Exception as e:
                errors["npcs"].append(f"NPC ID {npc_id}: {str(e)}")
                
        return errors


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例
    
    Returns:
        全局配置管理器实例
    """
    return config_manager