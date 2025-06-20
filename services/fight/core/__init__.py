"""
战斗服务核心模块
Fight Service Core Module

作者: lx
日期: 2025-06-18
描述: 战斗服务的核心组件
"""

from .battle_unit import (
    BattleUnit,
    BattleAttributes,
    Buff,
    BuffSystem,
    BuffEffect,
    BuffType,
    UnitState,
    AttributeType
)

from .battle_engine import (
    BattleEngine,
    BattleContext,
    ActionResult,
    RoundData,
    SkillConfig,
    SkillType,
    TargetType,
    DamageType,
    DamageCalculator,
    HitCalculator,
    TargetSelector,
    AIController
)

__all__ = [
    # Battle Unit
    "BattleUnit",
    "BattleAttributes", 
    "Buff",
    "BuffSystem",
    "BuffEffect",
    "BuffType",
    "UnitState",
    "AttributeType",
    
    # Battle Engine
    "BattleEngine",
    "BattleContext",
    "ActionResult",
    "RoundData",
    "SkillConfig",
    "SkillType",
    "TargetType",
    "DamageType",
    "DamageCalculator",
    "HitCalculator",
    "TargetSelector",
    "AIController"
]