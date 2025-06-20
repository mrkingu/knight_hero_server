"""
战斗服务模块
Fight Service Module

作者: lx
日期: 2025-06-18
描述: 战斗逻辑计算和技能效果处理
"""

from .core import (
    BattleUnit, BattleAttributes, Buff, BuffSystem, BuffEffect, BuffType, UnitState,
    BattleEngine, BattleContext, ActionResult, RoundData, SkillConfig, SkillType,
    TargetType, DamageType, DamageCalculator, HitCalculator, TargetSelector, AIController
)

from .handlers import (
    BattleHandler, BattleRequest, BattleReport, BattleStatistics, BattleCache,
    BattleType, BattleStatus, PlayerData
)

from .utils import (
    ObjectPool, AsyncObjectPool, PoolManager, get_pool_manager,
    create_battle_pool, get_battle_pool
)

__all__ = [
    # Core components
    "BattleUnit", "BattleAttributes", "Buff", "BuffSystem", "BuffEffect", "BuffType", "UnitState",
    "BattleEngine", "BattleContext", "ActionResult", "RoundData", "SkillConfig", "SkillType",
    "TargetType", "DamageType", "DamageCalculator", "HitCalculator", "TargetSelector", "AIController",
    
    # Handlers
    "BattleHandler", "BattleRequest", "BattleReport", "BattleStatistics", "BattleCache",
    "BattleType", "BattleStatus", "PlayerData",
    
    # Utils
    "ObjectPool", "AsyncObjectPool", "PoolManager", "get_pool_manager",
    "create_battle_pool", "get_battle_pool"
]