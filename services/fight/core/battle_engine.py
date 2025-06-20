"""
战斗引擎
Battle Engine

作者: lx
日期: 2025-06-18
描述: 战斗核心逻辑，包括技能计算、伤害公式和AI逻辑
"""
from typing import Dict, List, Optional, Any, Tuple, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import random
import math
import time
import asyncio
from concurrent.futures import ProcessPoolExecutor
import copy

from .battle_unit import (
    BattleUnit, BattleAttributes, Buff, BuffEffect, BuffType, UnitState
)
from ..utils.object_pool import ObjectPool, get_battle_pool, create_battle_pool


class SkillType(Enum):
    """技能类型"""
    ATTACK = "attack"        # 攻击技能
    HEAL = "heal"           # 治疗技能
    BUFF = "buff"           # 增益技能
    DEBUFF = "debuff"       # 减益技能
    CONTROL = "control"     # 控制技能
    SPECIAL = "special"     # 特殊技能


class TargetType(Enum):
    """目标类型"""
    SINGLE_ENEMY = "single_enemy"      # 单个敌人
    ALL_ENEMIES = "all_enemies"        # 所有敌人
    RANDOM_ENEMIES = "random_enemies"  # 随机敌人
    SINGLE_ALLY = "single_ally"        # 单个友军
    ALL_ALLIES = "all_allies"         # 所有友军
    SELF = "self"                     # 自己


class DamageType(Enum):
    """伤害类型"""
    PHYSICAL = "physical"   # 物理伤害
    MAGICAL = "magical"     # 魔法伤害
    TRUE = "true"          # 真实伤害
    POISON = "poison"      # 中毒伤害
    BURN = "burn"          # 燃烧伤害


@dataclass
class SkillConfig:
    """技能配置"""
    id: int
    name: str
    skill_type: SkillType
    target_type: TargetType
    damage_type: DamageType
    base_power: float                    # 基础威力
    power_scaling: float = 1.0           # 威力缩放
    accuracy: float = 1.0                # 命中率
    crit_rate_bonus: float = 0.0         # 暴击率加成
    crit_damage_bonus: float = 0.0       # 暴击伤害加成
    target_count: int = 1                # 目标数量
    cooldown: int = 0                    # 冷却回合
    cost: Dict[str, int] = field(default_factory=dict)  # 消耗（MP等）
    effects: List[Dict[str, Any]] = field(default_factory=list)  # 附加效果
    animation_time: float = 1.0          # 动画时间
    description: str = ""                # 技能描述


@dataclass
class ActionResult:
    """行动结果"""
    attacker_id: int
    skill_id: int
    targets: List[int]
    damages: List[int] = field(default_factory=list)
    heals: List[int] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    is_crit: List[bool] = field(default_factory=list)
    is_hit: List[bool] = field(default_factory=list)
    animation_time: float = 1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class RoundData:
    """回合数据"""
    round_number: int
    actions: List[ActionResult] = field(default_factory=list)
    unit_states: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    turn_order: List[int] = field(default_factory=list)
    round_time: float = 0.0


@dataclass
class BattleContext:
    """战斗上下文"""
    battle_id: str
    attacker_team: List[BattleUnit]
    defender_team: List[BattleUnit]
    current_round: int = 1
    max_rounds: int = 30
    winner: Optional[int] = None  # 0: 平局, 1: 攻击方, 2: 防守方
    is_finished: bool = False
    start_time: float = field(default_factory=time.time)
    total_damage: Dict[int, int] = field(default_factory=dict)
    total_heal: Dict[int, int] = field(default_factory=dict)
    
    def get_all_units(self) -> List[BattleUnit]:
        """获取所有单位"""
        return self.attacker_team + self.defender_team
    
    def get_alive_units(self, team_id: Optional[int] = None) -> List[BattleUnit]:
        """获取存活单位"""
        units = self.get_all_units()
        if team_id is not None:
            units = [u for u in units if u.team_id == team_id]
        return [u for u in units if u.is_alive()]
    
    def get_enemy_team(self, team_id: int) -> List[BattleUnit]:
        """获取敌方队伍"""
        if team_id == 1:
            return [u for u in self.defender_team if u.is_alive()]
        else:
            return [u for u in self.attacker_team if u.is_alive()]
    
    def get_ally_team(self, team_id: int) -> List[BattleUnit]:
        """获取友方队伍"""
        if team_id == 1:
            return [u for u in self.attacker_team if u.is_alive()]
        else:
            return [u for u in self.defender_team if u.is_alive()]
    
    def check_battle_end(self) -> bool:
        """检查战斗是否结束"""
        attacker_alive = any(u.is_alive() for u in self.attacker_team)
        defender_alive = any(u.is_alive() for u in self.defender_team)
        
        if not attacker_alive and not defender_alive:
            self.winner = 0  # 平局
            self.is_finished = True
        elif not defender_alive:
            self.winner = 1  # 攻击方胜利
            self.is_finished = True
        elif not attacker_alive:
            self.winner = 2  # 防守方胜利
            self.is_finished = True
        elif self.current_round >= self.max_rounds:
            # 回合数耗尽，判定防守方胜利
            self.winner = 2
            self.is_finished = True
            
        return self.is_finished


class DamageCalculator:
    """伤害计算器"""
    
    @staticmethod
    def calculate_damage(
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig,
        is_crit: bool = False
    ) -> int:
        """计算伤害
        
        Args:
            attacker: 攻击者
            defender: 防御者
            skill: 技能配置
            is_crit: 是否暴击
            
        Returns:
            int: 伤害值
        """
        # 基础伤害计算
        base_damage = 0
        
        if skill.damage_type == DamageType.PHYSICAL:
            base_damage = DamageCalculator._calculate_physical_damage(
                attacker, defender, skill
            )
        elif skill.damage_type == DamageType.MAGICAL:
            base_damage = DamageCalculator._calculate_magical_damage(
                attacker, defender, skill
            )
        elif skill.damage_type == DamageType.TRUE:
            base_damage = DamageCalculator._calculate_true_damage(
                attacker, defender, skill
            )
        
        # 暴击伤害
        if is_crit:
            crit_multiplier = attacker.current_attributes.crit_dmg + skill.crit_damage_bonus
            base_damage = int(base_damage * crit_multiplier)
        
        # 随机波动 (±10%)
        variance = random.uniform(0.9, 1.1)
        final_damage = max(1, int(base_damage * variance))
        
        return final_damage
    
    @staticmethod
    def _calculate_physical_damage(
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig
    ) -> float:
        """计算物理伤害"""
        atk = attacker.current_attributes.atk
        def_ = defender.current_attributes.def_
        
        # 基础公式: 攻击力 * 技能威力 - 防御力
        base_damage = atk * skill.base_power * skill.power_scaling - def_
        return max(1.0, base_damage)
    
    @staticmethod
    def _calculate_magical_damage(
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig
    ) -> float:
        """计算魔法伤害"""
        # 简化为使用攻击力，实际游戏中可能使用魔法攻击力
        atk = attacker.current_attributes.atk
        resist = defender.current_attributes.resist
        
        # 魔法伤害公式: 攻击力 * 技能威力 * (1 - 抗性)
        base_damage = atk * skill.base_power * skill.power_scaling * (1.0 - resist)
        return max(1.0, base_damage)
    
    @staticmethod
    def _calculate_true_damage(
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig
    ) -> float:
        """计算真实伤害（无视防御）"""
        atk = attacker.current_attributes.atk
        base_damage = atk * skill.base_power * skill.power_scaling
        return max(1.0, base_damage)
    
    @staticmethod
    def calculate_heal(
        caster: BattleUnit,
        target: BattleUnit,
        skill: SkillConfig
    ) -> int:
        """计算治疗量
        
        Args:
            caster: 施法者
            target: 目标
            skill: 技能配置
            
        Returns:
            int: 治疗量
        """
        # 基础治疗量 = 施法者攻击力 * 技能威力
        base_heal = caster.current_attributes.atk * skill.base_power
        
        # 随机波动
        variance = random.uniform(0.9, 1.1)
        final_heal = max(1, int(base_heal * variance))
        
        return final_heal


class HitCalculator:
    """命中计算器"""
    
    @staticmethod
    def calculate_hit(
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig
    ) -> bool:
        """计算是否命中
        
        Args:
            attacker: 攻击者
            defender: 防御者
            skill: 技能配置
            
        Returns:
            bool: 是否命中
        """
        # 基础命中率 = 攻击者命中 - 防御者闪避 + 技能命中
        hit_rate = (
            attacker.current_attributes.hit - 
            defender.current_attributes.dodge + 
            skill.accuracy
        )
        
        # 限制在 5% ~ 95% 之间
        hit_rate = max(0.05, min(0.95, hit_rate))
        
        return random.random() < hit_rate
    
    @staticmethod
    def calculate_crit(
        attacker: BattleUnit,
        skill: SkillConfig
    ) -> bool:
        """计算是否暴击
        
        Args:
            attacker: 攻击者
            skill: 技能配置
            
        Returns:
            bool: 是否暴击
        """
        crit_rate = attacker.current_attributes.crit + skill.crit_rate_bonus
        crit_rate = max(0.0, min(1.0, crit_rate))  # 限制在 0% ~ 100%
        
        return random.random() < crit_rate


class TargetSelector:
    """目标选择器"""
    
    @staticmethod
    def select_targets(
        caster: BattleUnit,
        context: BattleContext,
        skill: SkillConfig,
        primary_target: Optional[BattleUnit] = None
    ) -> List[BattleUnit]:
        """选择目标
        
        Args:
            caster: 施法者
            context: 战斗上下文
            skill: 技能配置
            primary_target: 主要目标
            
        Returns:
            List[BattleUnit]: 目标列表
        """
        if skill.target_type == TargetType.SELF:
            return [caster]
        
        elif skill.target_type == TargetType.SINGLE_ENEMY:
            enemies = context.get_enemy_team(caster.team_id)
            if primary_target and primary_target in enemies:
                return [primary_target]
            elif enemies:
                return [random.choice(enemies)]
            return []
        
        elif skill.target_type == TargetType.ALL_ENEMIES:
            return context.get_enemy_team(caster.team_id)
        
        elif skill.target_type == TargetType.RANDOM_ENEMIES:
            enemies = context.get_enemy_team(caster.team_id)
            count = min(skill.target_count, len(enemies))
            return random.sample(enemies, count) if count > 0 else []
        
        elif skill.target_type == TargetType.SINGLE_ALLY:
            allies = context.get_ally_team(caster.team_id)
            if primary_target and primary_target in allies:
                return [primary_target]
            elif allies:
                # 优先选择血量最少的友军
                return [min(allies, key=lambda u: u.current_attributes.hp)]
            return []
        
        elif skill.target_type == TargetType.ALL_ALLIES:
            return context.get_ally_team(caster.team_id)
        
        return []


class AIController:
    """AI控制器"""
    
    @staticmethod
    def select_skill(unit: BattleUnit, context: BattleContext, skills: Dict[int, SkillConfig]) -> Optional[SkillConfig]:
        """AI选择技能
        
        Args:
            unit: 战斗单位
            context: 战斗上下文
            skills: 可用技能
            
        Returns:
            Optional[SkillConfig]: 选择的技能
        """
        available_skills = [skills[skill_id] for skill_id in unit.skills if skill_id in skills]
        
        if not available_skills:
            return None
        
        # 简单AI逻辑
        if unit.ai_type == "aggressive":
            return AIController._select_aggressive_skill(unit, context, available_skills)
        elif unit.ai_type == "defensive":
            return AIController._select_defensive_skill(unit, context, available_skills)
        elif unit.ai_type == "support":
            return AIController._select_support_skill(unit, context, available_skills)
        else:
            return AIController._select_balanced_skill(unit, context, available_skills)
    
    @staticmethod
    def _select_aggressive_skill(
        unit: BattleUnit, 
        context: BattleContext, 
        skills: List[SkillConfig]
    ) -> SkillConfig:
        """攻击型AI选择技能"""
        # 优先选择攻击技能
        attack_skills = [s for s in skills if s.skill_type == SkillType.ATTACK]
        if attack_skills:
            return max(attack_skills, key=lambda s: s.base_power)
        return random.choice(skills)
    
    @staticmethod
    def _select_defensive_skill(
        unit: BattleUnit, 
        context: BattleContext, 
        skills: List[SkillConfig]
    ) -> SkillConfig:
        """防御型AI选择技能"""
        # 生命值低时优先治疗
        if unit.current_attributes.hp < unit.current_attributes.max_hp * 0.3:
            heal_skills = [s for s in skills if s.skill_type == SkillType.HEAL]
            if heal_skills:
                return random.choice(heal_skills)
        
        # 否则使用攻击技能
        attack_skills = [s for s in skills if s.skill_type == SkillType.ATTACK]
        if attack_skills:
            return random.choice(attack_skills)
        
        return random.choice(skills)
    
    @staticmethod
    def _select_support_skill(
        unit: BattleUnit, 
        context: BattleContext, 
        skills: List[SkillConfig]
    ) -> SkillConfig:
        """支援型AI选择技能"""
        allies = context.get_ally_team(unit.team_id)
        
        # 检查是否有友军需要治疗
        injured_allies = [ally for ally in allies if ally.current_attributes.hp < ally.current_attributes.max_hp * 0.5]
        if injured_allies:
            heal_skills = [s for s in skills if s.skill_type == SkillType.HEAL]
            if heal_skills:
                return random.choice(heal_skills)
        
        # 使用增益技能
        buff_skills = [s for s in skills if s.skill_type == SkillType.BUFF]
        if buff_skills:
            return random.choice(buff_skills)
        
        # 最后使用攻击技能
        return random.choice(skills)
    
    @staticmethod
    def _select_balanced_skill(
        unit: BattleUnit, 
        context: BattleContext, 
        skills: List[SkillConfig]
    ) -> SkillConfig:
        """平衡型AI选择技能"""
        # 随机选择，但有一定的权重
        weights = []
        for skill in skills:
            if skill.skill_type == SkillType.ATTACK:
                weights.append(3)
            elif skill.skill_type == SkillType.HEAL and unit.current_attributes.hp < unit.current_attributes.max_hp * 0.4:
                weights.append(2)
            else:
                weights.append(1)
        
        return random.choices(skills, weights=weights)[0]


class BattleEngine:
    """战斗引擎"""
    
    def __init__(self):
        """初始化战斗引擎"""
        # 预加载配置数据
        self.skill_configs: Dict[int, SkillConfig] = {}
        self.buff_configs: Dict[int, Dict[str, Any]] = {}
        
        # 对象池
        self.action_result_pool: Optional[ObjectPool] = None
        self.round_data_pool: Optional[ObjectPool] = None
        
        # 性能统计
        self.stats = {
            "battles_calculated": 0,
            "total_calculation_time": 0.0,
            "avg_calculation_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        # 结果缓存
        self.result_cache: Dict[str, Any] = {}
        
        # 进程池 (CPU密集型计算)
        self.process_pool: Optional[ProcessPoolExecutor] = None
        
        self._initialize_pools()
        self._load_default_skills()
    
    def _initialize_pools(self) -> None:
        """初始化对象池"""
        try:
            # 简单的对象池初始化，不用于复杂的数据结构
            self.action_result_pool = None  # 暂时不使用对象池
            self.round_data_pool = None     # 暂时不使用对象池
        except Exception:
            # 如果创建失败，创建本地池
            self.action_result_pool = None
            self.round_data_pool = None
    
    def _load_default_skills(self) -> None:
        """加载默认技能配置"""
        # 基础攻击
        self.skill_configs[1001] = SkillConfig(
            id=1001,
            name="普通攻击",
            skill_type=SkillType.ATTACK,
            target_type=TargetType.SINGLE_ENEMY,
            damage_type=DamageType.PHYSICAL,
            base_power=1.0,
            description="基础物理攻击"
        )
        
        # 强力攻击
        self.skill_configs[1002] = SkillConfig(
            id=1002,
            name="强力攻击",
            skill_type=SkillType.ATTACK,
            target_type=TargetType.SINGLE_ENEMY,
            damage_type=DamageType.PHYSICAL,
            base_power=1.5,
            crit_rate_bonus=0.1,
            description="威力更强的攻击，提高暴击率"
        )
        
        # 群体攻击
        self.skill_configs[1003] = SkillConfig(
            id=1003,
            name="群体攻击",
            skill_type=SkillType.ATTACK,
            target_type=TargetType.ALL_ENEMIES,
            damage_type=DamageType.PHYSICAL,
            base_power=0.8,
            description="攻击所有敌人"
        )
        
        # 治疗术
        self.skill_configs[2001] = SkillConfig(
            id=2001,
            name="治疗术",
            skill_type=SkillType.HEAL,
            target_type=TargetType.SINGLE_ALLY,
            damage_type=DamageType.MAGICAL,
            base_power=0.8,
            description="恢复友军生命值"
        )
    
    async def calculate_battle(self, context: BattleContext) -> List[RoundData]:
        """计算战斗结果
        
        Args:
            context: 战斗上下文
            
        Returns:
            List[RoundData]: 战斗回合数据
        """
        start_time = time.perf_counter()
        rounds_data = []
        
        try:
            # 初始化单位状态
            self._initialize_battle_units(context)
            
            # 战斗循环
            while not context.is_finished and context.current_round <= context.max_rounds:
                round_data = await self._process_round(context)
                rounds_data.append(round_data)
                
                # 检查战斗结束条件
                context.check_battle_end()
                context.current_round += 1
            
            # 更新统计
            calculation_time = time.perf_counter() - start_time
            self.stats["battles_calculated"] += 1
            self.stats["total_calculation_time"] += calculation_time
            self.stats["avg_calculation_time"] = (
                self.stats["total_calculation_time"] / self.stats["battles_calculated"]
            )
            
            return rounds_data
            
        except Exception as e:
            # 错误处理
            raise Exception(f"战斗计算失败: {str(e)}")
        
        finally:
            # 清理资源
            self._cleanup_battle_units(context)
    
    def _initialize_battle_units(self, context: BattleContext) -> None:
        """初始化战斗单位"""
        all_units = context.get_all_units()
        
        for i, unit in enumerate(all_units):
            unit.position = i
            unit.state = UnitState.READY
            unit.action_bar = 0.0
            
            # 设置默认技能
            if not unit.skills:
                unit.skills = [1001]  # 默认普通攻击
    
    def _cleanup_battle_units(self, context: BattleContext) -> None:
        """清理战斗单位"""
        for unit in context.get_all_units():
            # 回收到对象池（如果需要）
            pass
    
    async def _process_round(self, context: BattleContext) -> RoundData:
        """处理一个回合
        
        Args:
            context: 战斗上下文
            
        Returns:
            RoundData: 回合数据
        """
        round_start_time = time.perf_counter()
        
        # 创建回合数据
        round_data = RoundData(round_number=context.current_round)
        round_data.actions.clear()
        round_data.unit_states.clear()
        round_data.turn_order.clear()
        
        try:
            # 1. 计算行动顺序
            action_order = self._calculate_action_order(context)
            round_data.turn_order = [unit.id for unit in action_order]
            
            # 2. 回合开始处理
            self._process_round_start(context)
            
            # 3. 执行行动
            for unit in action_order:
                if unit.can_act() and not context.is_finished:
                    action_result = await self._execute_unit_action(unit, context)
                    if action_result:
                        round_data.actions.append(action_result)
                        
                        # 检查战斗是否结束
                        if context.check_battle_end():
                            break
            
            # 4. 回合结束处理
            self._process_round_end(context)
            
            # 5. 记录单位状态
            for unit in context.get_all_units():
                round_data.unit_states[unit.id] = unit.to_dict()
            
            round_data.round_time = time.perf_counter() - round_start_time
            
            return round_data
            
        except Exception as e:
            # 不需要归还对象到池
            raise e
    
    def _calculate_action_order(self, context: BattleContext) -> List[BattleUnit]:
        """计算行动顺序
        
        Args:
            context: 战斗上下文
            
        Returns:
            List[BattleUnit]: 按行动顺序排列的单位列表
        """
        alive_units = context.get_alive_units()
        
        # 按速度和优先级排序
        alive_units.sort(key=lambda unit: unit.get_action_priority(), reverse=True)
        
        return alive_units
    
    def _process_round_start(self, context: BattleContext) -> None:
        """处理回合开始"""
        for unit in context.get_all_units():
            unit.update_turn()
    
    def _process_round_end(self, context: BattleContext) -> None:
        """处理回合结束"""
        # 清理死亡单位的某些状态
        for unit in context.get_all_units():
            if unit.is_dead():
                unit.action_bar = 0.0
    
    async def _execute_unit_action(self, unit: BattleUnit, context: BattleContext) -> Optional[ActionResult]:
        """执行单位行动
        
        Args:
            unit: 行动单位
            context: 战斗上下文
            
        Returns:
            Optional[ActionResult]: 行动结果
        """
        # AI选择技能
        skill = AIController.select_skill(unit, context, self.skill_configs)
        if not skill:
            return None
        
        # 选择目标
        targets = TargetSelector.select_targets(unit, context, skill)
        if not targets:
            return None
        
        # 创建行动结果
        action_result = ActionResult(
            attacker_id=unit.id,
            skill_id=skill.id,
            targets=[t.id for t in targets]
        )
        
        action_result.attacker_id = unit.id
        action_result.skill_id = skill.id
        action_result.targets = [t.id for t in targets]
        action_result.damages.clear()
        action_result.heals.clear()
        action_result.effects.clear()
        action_result.is_crit.clear()
        action_result.is_hit.clear()
        action_result.animation_time = skill.animation_time
        action_result.timestamp = time.time()
        
        # 执行技能效果
        for target in targets:
            await self._apply_skill_effect(unit, target, skill, action_result, context)
        
        return action_result
    
    async def _apply_skill_effect(
        self,
        caster: BattleUnit,
        target: BattleUnit,
        skill: SkillConfig,
        action_result: ActionResult,
        context: BattleContext
    ) -> None:
        """应用技能效果
        
        Args:
            caster: 施法者
            target: 目标
            skill: 技能配置
            action_result: 行动结果
            context: 战斗上下文
        """
        # 计算命中
        is_hit = HitCalculator.calculate_hit(caster, target, skill)
        action_result.is_hit.append(is_hit)
        
        if not is_hit:
            action_result.damages.append(0)
            action_result.heals.append(0)
            action_result.is_crit.append(False)
            return
        
        # 根据技能类型处理
        if skill.skill_type == SkillType.ATTACK:
            await self._apply_damage_effect(caster, target, skill, action_result, context)
        elif skill.skill_type == SkillType.HEAL:
            await self._apply_heal_effect(caster, target, skill, action_result, context)
        elif skill.skill_type in [SkillType.BUFF, SkillType.DEBUFF]:
            await self._apply_buff_effect(caster, target, skill, action_result, context)
        elif skill.skill_type == SkillType.CONTROL:
            await self._apply_control_effect(caster, target, skill, action_result, context)
    
    async def _apply_damage_effect(
        self,
        attacker: BattleUnit,
        defender: BattleUnit,
        skill: SkillConfig,
        action_result: ActionResult,
        context: BattleContext
    ) -> None:
        """应用伤害效果"""
        # 计算暴击
        is_crit = HitCalculator.calculate_crit(attacker, skill)
        action_result.is_crit.append(is_crit)
        
        # 计算伤害
        damage = DamageCalculator.calculate_damage(attacker, defender, skill, is_crit)
        
        # 应用伤害
        actual_damage = defender.take_damage(damage, skill.damage_type.value)
        action_result.damages.append(actual_damage)
        action_result.heals.append(0)
        
        # 更新统计
        if attacker.id not in context.total_damage:
            context.total_damage[attacker.id] = 0
        context.total_damage[attacker.id] += actual_damage
    
    async def _apply_heal_effect(
        self,
        caster: BattleUnit,
        target: BattleUnit,
        skill: SkillConfig,
        action_result: ActionResult,
        context: BattleContext
    ) -> None:
        """应用治疗效果"""
        action_result.is_crit.append(False)
        
        # 计算治疗量
        heal_amount = DamageCalculator.calculate_heal(caster, target, skill)
        
        # 应用治疗
        actual_heal = target.heal(heal_amount)
        action_result.damages.append(0)
        action_result.heals.append(actual_heal)
        
        # 更新统计
        if caster.id not in context.total_heal:
            context.total_heal[caster.id] = 0
        context.total_heal[caster.id] += actual_heal
    
    async def _apply_buff_effect(
        self,
        caster: BattleUnit,
        target: BattleUnit,
        skill: SkillConfig,
        action_result: ActionResult,
        context: BattleContext
    ) -> None:
        """应用Buff效果"""
        action_result.is_crit.append(False)
        action_result.damages.append(0)
        action_result.heals.append(0)
        
        # 处理技能附加效果
        for effect_data in skill.effects:
            effect_type = effect_data.get("type")
            if effect_type in ["buff", "debuff"]:
                buff = self._create_buff_from_effect(effect_data, caster.id)
                if buff:
                    target.add_buff(buff)
                    action_result.effects.append({
                        "type": "buff_applied",
                        "buff_id": buff.id,
                        "target_id": target.id
                    })
    
    async def _apply_control_effect(
        self,
        caster: BattleUnit,
        target: BattleUnit,
        skill: SkillConfig,
        action_result: ActionResult,
        context: BattleContext
    ) -> None:
        """应用控制效果"""
        action_result.is_crit.append(False)
        action_result.damages.append(0)
        action_result.heals.append(0)
        
        # 控制效果通常通过Buff实现
        await self._apply_buff_effect(caster, target, skill, action_result, context)
    
    def _create_buff_from_effect(self, effect_data: Dict[str, Any], source_unit_id: int) -> Optional[Buff]:
        """从效果数据创建Buff
        
        Args:
            effect_data: 效果数据
            source_unit_id: 来源单位ID
            
        Returns:
            Optional[Buff]: 创建的Buff
        """
        try:
            buff_effect = BuffEffect(effect_data.get("effect", ""))
            buff_type = BuffType.POSITIVE if effect_data.get("type") == "buff" else BuffType.NEGATIVE
            
            return Buff(
                id=effect_data.get("id", 0),
                name=effect_data.get("name", ""),
                buff_type=buff_type,
                effect=buff_effect,
                value=effect_data.get("value", 0),
                duration=effect_data.get("duration", 1),
                remaining_turns=effect_data.get("duration", 1),
                source_unit_id=source_unit_id
            )
        except Exception:
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息"""
        return self.stats.copy()
    
    def clear_cache(self) -> None:
        """清理缓存"""
        self.result_cache.clear()
    
    def shutdown(self) -> None:
        """关闭引擎"""
        if self.process_pool:
            self.process_pool.shutdown(wait=True)