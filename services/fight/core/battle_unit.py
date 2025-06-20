"""
战斗单位
Battle Unit

作者: lx
日期: 2025-06-18  
描述: 战斗单位的定义，包括属性计算、Buff系统和状态机
"""
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import time
import copy
from abc import ABC, abstractmethod


class UnitState(IntEnum):
    """战斗单位状态"""
    IDLE = 0      # 空闲
    READY = 1     # 准备
    ACTING = 2    # 行动中
    DEAD = 3      # 死亡
    STUNNED = 4   # 眩晕
    FROZEN = 5    # 冰冻


class AttributeType(Enum):
    """属性类型"""
    HP = "hp"           # 生命值
    MAX_HP = "max_hp"   # 最大生命值
    ATK = "atk"         # 攻击力
    DEF = "def"         # 防御力
    SPD = "spd"         # 速度
    CRIT = "crit"       # 暴击率
    CRIT_DMG = "crit_dmg"  # 暴击伤害
    HIT = "hit"         # 命中率
    DODGE = "dodge"     # 闪避率
    RESIST = "resist"   # 抗性


class BuffType(Enum):
    """Buff类型"""
    POSITIVE = "positive"  # 正面效果
    NEGATIVE = "negative"  # 负面效果
    NEUTRAL = "neutral"    # 中性效果


class BuffEffect(Enum):
    """Buff效果类型"""
    ATK_BOOST = "atk_boost"      # 攻击力提升
    DEF_BOOST = "def_boost"      # 防御力提升
    SPD_BOOST = "spd_boost"      # 速度提升
    ATK_REDUCE = "atk_reduce"    # 攻击力降低
    DEF_REDUCE = "def_reduce"    # 防御力降低
    SPD_REDUCE = "spd_reduce"    # 速度降低
    POISON = "poison"            # 中毒
    HEAL = "heal"               # 治疗
    SHIELD = "shield"           # 护盾
    STUN = "stun"               # 眩晕
    FREEZE = "freeze"           # 冰冻


@dataclass
class Buff:
    """Buff数据结构"""
    
    id: int                                    # Buff ID
    name: str                                  # Buff名称
    buff_type: BuffType                        # Buff类型
    effect: BuffEffect                         # 效果类型
    value: float                               # 效果数值
    duration: int                              # 持续回合数
    remaining_turns: int                       # 剩余回合数
    stack_count: int = 1                       # 叠加层数
    max_stack: int = 1                         # 最大叠加层数
    can_dispel: bool = True                    # 是否可以驱散
    trigger_timing: str = "turn_start"         # 触发时机
    source_unit_id: Optional[int] = None       # 来源单位ID
    custom_data: Dict[str, Any] = field(default_factory=dict)  # 自定义数据
    
    def is_expired(self) -> bool:
        """检查Buff是否过期"""
        return self.remaining_turns <= 0
    
    def reduce_turn(self) -> None:
        """减少一回合"""
        self.remaining_turns -= 1
    
    def add_stack(self, count: int = 1) -> bool:
        """增加叠加层数
        
        Args:
            count: 增加的层数
            
        Returns:
            bool: 是否成功增加
        """
        if self.stack_count + count <= self.max_stack:
            self.stack_count += count
            return True
        else:
            self.stack_count = self.max_stack
            return False
    
    def get_total_value(self) -> float:
        """获取总效果值（考虑叠加）"""
        return self.value * self.stack_count
    
    def reset(self) -> None:
        """重置Buff状态"""
        self.remaining_turns = self.duration
        self.stack_count = 1
        self.custom_data.clear()


@dataclass 
class BattleAttributes:
    """战斗属性"""
    
    # 基础属性
    hp: int = 100
    max_hp: int = 100
    atk: int = 50
    def_: int = 30
    spd: int = 100
    
    # 二级属性
    crit: float = 0.05      # 暴击率 5%
    crit_dmg: float = 1.5   # 暴击伤害 150%
    hit: float = 0.95       # 命中率 95%
    dodge: float = 0.05     # 闪避率 5%
    resist: float = 0.0     # 抗性 0%
    
    def copy(self) -> 'BattleAttributes':
        """复制属性"""
        return BattleAttributes(
            hp=self.hp,
            max_hp=self.max_hp,
            atk=self.atk,
            def_=self.def_,
            spd=self.spd,
            crit=self.crit,
            crit_dmg=self.crit_dmg,
            hit=self.hit,
            dodge=self.dodge,
            resist=self.resist
        )
    
    def reset(self) -> None:
        """重置属性"""
        self.hp = self.max_hp


class BuffSystem:
    """Buff系统"""
    
    def __init__(self):
        self.buffs: Dict[int, Buff] = {}  # 按ID存储的Buff
        self.effect_buffs: Dict[BuffEffect, List[Buff]] = {}  # 按效果类型分组的Buff
        
    def add_buff(self, buff: Buff) -> bool:
        """添加Buff
        
        Args:
            buff: 要添加的Buff
            
        Returns:
            bool: 是否成功添加
        """
        # 检查是否已存在相同Buff
        if buff.id in self.buffs:
            existing_buff = self.buffs[buff.id]
            # 如果可以叠加，增加层数
            if existing_buff.add_stack():
                existing_buff.remaining_turns = max(existing_buff.remaining_turns, buff.remaining_turns)
                return True
            else:
                # 刷新持续时间
                existing_buff.remaining_turns = buff.remaining_turns
                return True
        else:
            # 添加新Buff
            self.buffs[buff.id] = buff
            
            # 按效果分组
            if buff.effect not in self.effect_buffs:
                self.effect_buffs[buff.effect] = []
            self.effect_buffs[buff.effect].append(buff)
            
            return True
    
    def remove_buff(self, buff_id: int) -> bool:
        """移除Buff
        
        Args:
            buff_id: Buff ID
            
        Returns:
            bool: 是否成功移除
        """
        if buff_id in self.buffs:
            buff = self.buffs.pop(buff_id)
            
            # 从效果分组中移除
            if buff.effect in self.effect_buffs:
                self.effect_buffs[buff.effect].remove(buff)
                if not self.effect_buffs[buff.effect]:
                    del self.effect_buffs[buff.effect]
                    
            return True
        return False
    
    def get_buffs_by_effect(self, effect: BuffEffect) -> List[Buff]:
        """获取指定效果的所有Buff
        
        Args:
            effect: 效果类型
            
        Returns:
            List[Buff]: Buff列表
        """
        return self.effect_buffs.get(effect, []).copy()
    
    def get_buffs_by_type(self, buff_type: BuffType) -> List[Buff]:
        """获取指定类型的所有Buff
        
        Args:
            buff_type: Buff类型
            
        Returns:
            List[Buff]: Buff列表
        """
        return [buff for buff in self.buffs.values() if buff.buff_type == buff_type]
    
    def dispel_buffs(self, buff_type: Optional[BuffType] = None, count: int = 1) -> List[Buff]:
        """驱散Buff
        
        Args:
            buff_type: 要驱散的Buff类型，None表示全部
            count: 驱散数量
            
        Returns:
            List[Buff]: 被驱散的Buff列表
        """
        dispelled = []
        target_buffs = []
        
        # 筛选可驱散的Buff
        for buff in self.buffs.values():
            if buff.can_dispel and (buff_type is None or buff.buff_type == buff_type):
                target_buffs.append(buff)
        
        # 按优先级排序（负面Buff优先）
        target_buffs.sort(key=lambda b: (b.buff_type != BuffType.NEGATIVE, b.id))
        
        # 驱散指定数量的Buff
        for i in range(min(count, len(target_buffs))):
            buff = target_buffs[i]
            if self.remove_buff(buff.id):
                dispelled.append(buff)
                
        return dispelled
    
    def update_turn(self) -> List[Buff]:
        """更新回合，处理Buff持续时间
        
        Returns:
            List[Buff]: 过期的Buff列表
        """
        expired_buffs = []
        
        for buff_id, buff in list(self.buffs.items()):
            buff.reduce_turn()
            if buff.is_expired():
                self.remove_buff(buff_id)
                expired_buffs.append(buff)
                
        return expired_buffs
    
    def clear(self) -> None:
        """清空所有Buff"""
        self.buffs.clear()
        self.effect_buffs.clear()
    
    def reset(self) -> None:
        """重置所有Buff状态"""
        for buff in self.buffs.values():
            buff.reset()


class BattleUnit:
    """战斗单位
    
    使用__slots__优化内存，实现状态机模式
    """
    
    __slots__ = [
        'id', 'name', 'unit_type', 'level', 'base_attributes', 'current_attributes',
        'state', 'buff_system', 'skills', 'ai_type', 'position', 'team_id',
        'action_bar', 'last_action_time', 'combat_data', '_state_handlers'
    ]
    
    def __init__(
        self,
        unit_id: int,
        name: str,
        unit_type: str = "normal",
        level: int = 1,
        attributes: Optional[BattleAttributes] = None
    ):
        """初始化战斗单位
        
        Args:
            unit_id: 单位ID
            name: 单位名称
            unit_type: 单位类型
            level: 等级
            attributes: 属性数据
        """
        self.id = unit_id
        self.name = name
        self.unit_type = unit_type
        self.level = level
        
        # 属性系统
        self.base_attributes = attributes or BattleAttributes()
        self.current_attributes = self.base_attributes.copy()
        
        # 状态系统
        self.state = UnitState.IDLE
        self.buff_system = BuffSystem()
        
        # 战斗相关
        self.skills: List[int] = []  # 技能ID列表
        self.ai_type: str = "normal"
        self.position: int = 0
        self.team_id: int = 0
        self.action_bar: float = 0.0  # 行动条
        self.last_action_time: float = 0.0
        
        # 战斗数据
        self.combat_data: Dict[str, Any] = {}
        
        # 状态处理器
        self._state_handlers: Dict[UnitState, Callable] = {
            UnitState.IDLE: self._handle_idle,
            UnitState.READY: self._handle_ready,
            UnitState.ACTING: self._handle_acting,
            UnitState.DEAD: self._handle_dead,
            UnitState.STUNNED: self._handle_stunned,
            UnitState.FROZEN: self._handle_frozen,
        }
    
    def reset(self) -> None:
        """重置单位状态"""
        self.current_attributes = self.base_attributes.copy()
        self.current_attributes.reset()
        self.state = UnitState.IDLE
        self.buff_system.clear()
        self.action_bar = 0.0
        self.last_action_time = 0.0
        self.combat_data.clear()
    
    def is_alive(self) -> bool:
        """检查是否存活"""
        return self.current_attributes.hp > 0 and self.state != UnitState.DEAD
    
    def is_dead(self) -> bool:
        """检查是否死亡"""
        return not self.is_alive()
    
    def can_act(self) -> bool:
        """检查是否可以行动"""
        return (self.is_alive() and 
                self.state not in [UnitState.DEAD, UnitState.STUNNED, UnitState.FROZEN])
    
    def take_damage(self, damage: int, damage_type: str = "physical") -> int:
        """受到伤害
        
        Args:
            damage: 伤害值
            damage_type: 伤害类型
            
        Returns:
            int: 实际伤害值
        """
        if not self.is_alive():
            return 0
        
        # 检查护盾Buff
        shield_buffs = self.buff_system.get_buffs_by_effect(BuffEffect.SHIELD)
        remaining_damage = damage
        
        for shield_buff in shield_buffs:
            if remaining_damage <= 0:
                break
                
            shield_value = shield_buff.get_total_value()
            absorbed = min(remaining_damage, shield_value)
            remaining_damage -= absorbed
            shield_buff.value -= absorbed
            
            # 如果护盾耗尽，移除Buff
            if shield_buff.value <= 0:
                self.buff_system.remove_buff(shield_buff.id)
        
        # 计算实际伤害
        actual_damage = min(remaining_damage, self.current_attributes.hp)
        self.current_attributes.hp -= actual_damage
        
        # 检查死亡
        if self.current_attributes.hp <= 0:
            self.current_attributes.hp = 0
            self.change_state(UnitState.DEAD)
            
        return actual_damage
    
    def heal(self, amount: int) -> int:
        """治疗
        
        Args:
            amount: 治疗量
            
        Returns:
            int: 实际治疗量
        """
        if not self.is_alive():
            return 0
            
        max_heal = self.current_attributes.max_hp - self.current_attributes.hp
        actual_heal = min(amount, max_heal)
        self.current_attributes.hp += actual_heal
        
        return actual_heal
    
    def add_buff(self, buff: Buff) -> bool:
        """添加Buff
        
        Args:
            buff: Buff对象
            
        Returns:
            bool: 是否成功添加
        """
        success = self.buff_system.add_buff(buff)
        if success:
            self._apply_buff_effects()
        return success
    
    def remove_buff(self, buff_id: int) -> bool:
        """移除Buff
        
        Args:
            buff_id: Buff ID
            
        Returns:
            bool: 是否成功移除
        """
        success = self.buff_system.remove_buff(buff_id)
        if success:
            self._apply_buff_effects()
        return success
    
    def _apply_buff_effects(self) -> None:
        """应用Buff效果到属性"""
        # 重置为基础属性
        self.current_attributes = self.base_attributes.copy()
        
        # 应用所有Buff效果
        for buff in self.buff_system.buffs.values():
            self._apply_single_buff(buff)
    
    def _apply_single_buff(self, buff: Buff) -> None:
        """应用单个Buff效果
        
        Args:
            buff: Buff对象
        """
        effect_value = buff.get_total_value()
        
        if buff.effect == BuffEffect.ATK_BOOST:
            self.current_attributes.atk += int(effect_value)
        elif buff.effect == BuffEffect.ATK_REDUCE:
            self.current_attributes.atk = max(1, self.current_attributes.atk - int(effect_value))
        elif buff.effect == BuffEffect.DEF_BOOST:
            self.current_attributes.def_ += int(effect_value)
        elif buff.effect == BuffEffect.DEF_REDUCE:
            self.current_attributes.def_ = max(0, self.current_attributes.def_ - int(effect_value))
        elif buff.effect == BuffEffect.SPD_BOOST:
            self.current_attributes.spd += int(effect_value)
        elif buff.effect == BuffEffect.SPD_REDUCE:
            self.current_attributes.spd = max(1, self.current_attributes.spd - int(effect_value))
        elif buff.effect == BuffEffect.STUN:
            self.change_state(UnitState.STUNNED)
        elif buff.effect == BuffEffect.FREEZE:
            self.change_state(UnitState.FROZEN)
    
    def change_state(self, new_state: UnitState) -> None:
        """改变状态
        
        Args:
            new_state: 新状态
        """
        old_state = self.state
        self.state = new_state
        
        # 触发状态处理器
        if new_state in self._state_handlers:
            self._state_handlers[new_state]()
    
    def update_turn(self) -> None:
        """更新回合"""
        # 更新Buff
        expired_buffs = self.buff_system.update_turn()
        
        # 重新应用Buff效果
        if expired_buffs:
            self._apply_buff_effects()
            
        # 处理持续伤害/治疗
        self._process_dot_effects()
        
        # 更新状态
        self._update_state()
    
    def _process_dot_effects(self) -> None:
        """处理持续伤害/治疗效果"""
        # 处理中毒
        poison_buffs = self.buff_system.get_buffs_by_effect(BuffEffect.POISON)
        for poison_buff in poison_buffs:
            damage = int(poison_buff.get_total_value())
            self.take_damage(damage, "poison")
        
        # 处理治疗
        heal_buffs = self.buff_system.get_buffs_by_effect(BuffEffect.HEAL)
        for heal_buff in heal_buffs:
            heal_amount = int(heal_buff.get_total_value())
            self.heal(heal_amount)
    
    def _update_state(self) -> None:
        """更新状态"""
        # 如果死亡，直接设为死亡状态
        if self.current_attributes.hp <= 0:
            self.change_state(UnitState.DEAD)
            return
            
        # 检查是否有控制效果
        if self.buff_system.get_buffs_by_effect(BuffEffect.STUN):
            self.change_state(UnitState.STUNNED)
        elif self.buff_system.get_buffs_by_effect(BuffEffect.FREEZE):
            self.change_state(UnitState.FROZEN)
        elif self.state in [UnitState.STUNNED, UnitState.FROZEN]:
            # 如果没有控制效果但当前是控制状态，恢复为空闲
            self.change_state(UnitState.IDLE)
    
    def get_effective_speed(self) -> float:
        """获取有效速度（考虑状态影响）"""
        if self.state in [UnitState.DEAD, UnitState.STUNNED, UnitState.FROZEN]:
            return 0.0
        return float(self.current_attributes.spd)
    
    def get_action_priority(self) -> float:
        """获取行动优先级"""
        speed = self.get_effective_speed()
        # 速度越高，优先级越高，同时加入一些随机性
        import random
        return speed + random.random() * 10
    
    # 状态处理器方法
    def _handle_idle(self) -> None:
        """处理空闲状态"""
        pass
    
    def _handle_ready(self) -> None:
        """处理准备状态"""
        pass
    
    def _handle_acting(self) -> None:
        """处理行动状态"""
        pass
    
    def _handle_dead(self) -> None:
        """处理死亡状态"""
        self.action_bar = 0.0
    
    def _handle_stunned(self) -> None:
        """处理眩晕状态"""
        pass
    
    def _handle_frozen(self) -> None:
        """处理冰冻状态"""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "unit_type": self.unit_type,
            "level": self.level,
            "state": self.state.value,
            "attributes": {
                "hp": self.current_attributes.hp,
                "max_hp": self.current_attributes.max_hp,
                "atk": self.current_attributes.atk,
                "def": self.current_attributes.def_,
                "spd": self.current_attributes.spd,
                "crit": self.current_attributes.crit,
                "crit_dmg": self.current_attributes.crit_dmg,
                "hit": self.current_attributes.hit,
                "dodge": self.current_attributes.dodge,
                "resist": self.current_attributes.resist
            },
            "buffs": [
                {
                    "id": buff.id,
                    "name": buff.name,
                    "effect": buff.effect.value,
                    "value": buff.value,
                    "remaining_turns": buff.remaining_turns,
                    "stack_count": buff.stack_count
                }
                for buff in self.buff_system.buffs.values()
            ],
            "position": self.position,
            "team_id": self.team_id,
            "action_bar": self.action_bar
        }