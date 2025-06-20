"""
战斗处理器
Battle Handler

作者: lx
日期: 2025-06-18
描述: 处理PVE和PVP战斗，生成战斗报告
"""
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import time
import asyncio
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import json

from ..core.battle_engine import (
    BattleEngine, BattleContext, RoundData, ActionResult
)
from ..core.battle_unit import (
    BattleUnit, BattleAttributes, UnitState
)
from ..utils.object_pool import get_pool_manager


class BattleType(Enum):
    """战斗类型"""
    PVE = "pve"          # 玩家vs环境
    PVP = "pvp"          # 玩家vs玩家
    ARENA = "arena"      # 竞技场
    RAID = "raid"        # 团队副本
    GUILD_WAR = "guild_war"  # 公会战


class BattleStatus(Enum):
    """战斗状态"""
    PENDING = "pending"      # 等待中
    RUNNING = "running"      # 进行中
    FINISHED = "finished"    # 已完成
    ERROR = "error"         # 错误
    TIMEOUT = "timeout"     # 超时


@dataclass
class PlayerData:
    """玩家数据"""
    player_id: int
    name: str
    level: int
    units: List[Dict[str, Any]]      # 单位数据列表
    formation: List[int] = field(default_factory=list)  # 阵型
    team_power: int = 0              # 队伍战力
    buffs: List[Dict[str, Any]] = field(default_factory=list)  # 队伍Buff


@dataclass
class BattleRequest:
    """战斗请求"""
    battle_id: str
    battle_type: BattleType
    attacker: PlayerData
    defender: PlayerData
    settings: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class BattleStatistics:
    """战斗统计"""
    total_damage: Dict[int, int] = field(default_factory=dict)
    total_heal: Dict[int, int] = field(default_factory=dict)
    kills: Dict[int, int] = field(default_factory=dict)
    deaths: Dict[int, int] = field(default_factory=dict)
    skill_usage: Dict[int, Dict[int, int]] = field(default_factory=dict)
    damage_taken: Dict[int, int] = field(default_factory=dict)
    heal_received: Dict[int, int] = field(default_factory=dict)
    max_damage_single: Dict[int, int] = field(default_factory=dict)
    survival_time: Dict[int, int] = field(default_factory=dict)


@dataclass
class BattleReport:
    """战斗报告"""
    battle_id: str
    battle_type: BattleType
    status: BattleStatus
    winner: Optional[int] = None     # 0: 平局, 1: 攻击方, 2: 防守方
    rounds: List[RoundData] = field(default_factory=list)
    statistics: Optional[BattleStatistics] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: float = 0.0
    rewards: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "battle_id": self.battle_id,
            "battle_type": self.battle_type.value,
            "status": self.status.value,
            "winner": self.winner,
            "rounds_count": len(self.rounds),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "statistics": self.statistics.__dict__ if self.statistics else None,
            "rewards": self.rewards,
            "error_message": self.error_message
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class BattleCache:
    """战斗缓存系统"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._cache: Dict[str, BattleReport] = {}
        self._access_times: Dict[str, float] = {}
    
    def get(self, battle_id: str) -> Optional[BattleReport]:
        """获取缓存的战斗报告"""
        if battle_id in self._cache:
            self._access_times[battle_id] = time.time()
            return self._cache[battle_id]
        return None
    
    def put(self, battle_id: str, report: BattleReport) -> None:
        """缓存战斗报告"""
        # 如果缓存已满，清理最旧的条目
        if len(self._cache) >= self.max_size:
            self._cleanup_old_entries()
        
        self._cache[battle_id] = report
        self._access_times[battle_id] = time.time()
    
    def remove(self, battle_id: str) -> bool:
        """移除缓存条目"""
        if battle_id in self._cache:
            del self._cache[battle_id]
            del self._access_times[battle_id]
            return True
        return False
    
    def _cleanup_old_entries(self) -> None:
        """清理旧条目"""
        # 移除最旧的10%条目
        cleanup_count = max(1, self.max_size // 10)
        
        # 按访问时间排序
        sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])
        
        for battle_id, _ in sorted_items[:cleanup_count]:
            if battle_id in self._cache:
                del self._cache[battle_id]
            if battle_id in self._access_times:
                del self._access_times[battle_id]
    
    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._access_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self._cache),
            "max_size": self.max_size,
            "cache_usage": len(self._cache) / self.max_size * 100
        }


class BattleHandler:
    """战斗处理器"""
    
    def __init__(self):
        """初始化战斗处理器"""
        self.battle_engine = BattleEngine()
        self.cache = BattleCache()
        
        # 线程池用于I/O密集型任务
        self.io_executor = ThreadPoolExecutor(
            max_workers=10, 
            thread_name_prefix="battle_io"
        )
        
        # 进程池用于CPU密集型任务
        self.cpu_executor = ProcessPoolExecutor(
            max_workers=4,
            mp_context=None  # 使用默认的multiprocessing context
        )
        
        # 统计信息
        self.stats = {
            "total_battles": 0,
            "pve_battles": 0,
            "pvp_battles": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_battle_time": 0.0,
            "total_battle_time": 0.0,
            "error_count": 0
        }
    
    async def process_battle(self, request: BattleRequest) -> BattleReport:
        """处理战斗请求
        
        Args:
            request: 战斗请求
            
        Returns:
            BattleReport: 战斗报告
        """
        start_time = time.perf_counter()
        
        # 检查缓存
        cached_report = self.cache.get(request.battle_id)
        if cached_report:
            self.stats["cache_hits"] += 1
            return cached_report
        
        self.stats["cache_misses"] += 1
        
        # 创建战斗报告
        report = BattleReport(
            battle_id=request.battle_id,
            battle_type=request.battle_type,
            status=BattleStatus.RUNNING
        )
        
        try:
            # 根据战斗类型处理
            if request.battle_type == BattleType.PVE:
                await self._process_pve_battle(request, report)
            elif request.battle_type == BattleType.PVP:
                await self._process_pvp_battle(request, report)
            elif request.battle_type == BattleType.ARENA:
                await self._process_arena_battle(request, report)
            else:
                await self._process_generic_battle(request, report)
            
            # 完成战斗
            report.status = BattleStatus.FINISHED
            report.end_time = time.time()
            report.duration = report.end_time - report.start_time
            
            # 计算奖励
            report.rewards = self._calculate_rewards(request, report)
            
            # 更新统计
            self.stats["total_battles"] += 1
            if request.battle_type == BattleType.PVE:
                self.stats["pve_battles"] += 1
            elif request.battle_type == BattleType.PVP:
                self.stats["pvp_battles"] += 1
            
            battle_time = time.perf_counter() - start_time
            self.stats["total_battle_time"] += battle_time
            self.stats["avg_battle_time"] = (
                self.stats["total_battle_time"] / self.stats["total_battles"]
            )
            
            # 缓存结果
            self.cache.put(request.battle_id, report)
            
            return report
            
        except Exception as e:
            # 错误处理
            report.status = BattleStatus.ERROR
            report.error_message = str(e)
            report.end_time = time.time()
            report.duration = report.end_time - report.start_time
            
            self.stats["error_count"] += 1
            
            return report
    
    async def _process_pve_battle(self, request: BattleRequest, report: BattleReport) -> None:
        """处理PVE战斗
        
        Args:
            request: 战斗请求
            report: 战斗报告
        """
        # 创建战斗上下文
        context = await self._create_battle_context(request)
        
        # PVE特殊设置
        context.max_rounds = request.settings.get("max_rounds", 30)
        
        # 执行战斗计算
        rounds_data = await self.battle_engine.calculate_battle(context)
        
        # 填充报告
        report.rounds = rounds_data
        report.winner = context.winner
        report.statistics = self._calculate_statistics(context, rounds_data)
    
    async def _process_pvp_battle(self, request: BattleRequest, report: BattleReport) -> None:
        """处理PVP战斗
        
        Args:
            request: 战斗请求
            report: 战斗报告
        """
        # 创建战斗上下文
        context = await self._create_battle_context(request)
        
        # PVP特殊设置
        context.max_rounds = request.settings.get("max_rounds", 20)  # PVP回合数较少
        
        # 执行战斗计算
        rounds_data = await self.battle_engine.calculate_battle(context)
        
        # 填充报告
        report.rounds = rounds_data
        report.winner = context.winner
        report.statistics = self._calculate_statistics(context, rounds_data)
    
    async def _process_arena_battle(self, request: BattleRequest, report: BattleReport) -> None:
        """处理竞技场战斗
        
        Args:
            request: 战斗请求
            report: 战斗报告
        """
        # 竞技场战斗类似PVP，但有特殊规则
        await self._process_pvp_battle(request, report)
        
        # 竞技场特殊处理
        # 例如：排名计算、特殊奖励等
    
    async def _process_generic_battle(self, request: BattleRequest, report: BattleReport) -> None:
        """处理通用战斗
        
        Args:
            request: 战斗请求
            report: 战斗报告
        """
        # 通用战斗处理
        await self._process_pve_battle(request, report)
    
    async def _create_battle_context(self, request: BattleRequest) -> BattleContext:
        """创建战斗上下文
        
        Args:
            request: 战斗请求
            
        Returns:
            BattleContext: 战斗上下文
        """
        # 创建攻击方队伍
        attacker_team = await self._create_battle_units(request.attacker, team_id=1)
        
        # 创建防守方队伍
        defender_team = await self._create_battle_units(request.defender, team_id=2)
        
        # 创建战斗上下文
        context = BattleContext(
            battle_id=request.battle_id,
            attacker_team=attacker_team,
            defender_team=defender_team
        )
        
        return context
    
    async def _create_battle_units(self, player_data: PlayerData, team_id: int) -> List[BattleUnit]:
        """创建战斗单位
        
        Args:
            player_data: 玩家数据
            team_id: 队伍ID
            
        Returns:
            List[BattleUnit]: 战斗单位列表
        """
        units = []
        
        for i, unit_data in enumerate(player_data.units):
            # 创建属性
            attributes = BattleAttributes(
                hp=unit_data.get("hp", 100),
                max_hp=unit_data.get("max_hp", 100),
                atk=unit_data.get("atk", 50),
                def_=unit_data.get("def", 30),
                spd=unit_data.get("spd", 100),
                crit=unit_data.get("crit", 0.05),
                crit_dmg=unit_data.get("crit_dmg", 1.5),
                hit=unit_data.get("hit", 0.95),
                dodge=unit_data.get("dodge", 0.05),
                resist=unit_data.get("resist", 0.0)
            )
            
            # 创建战斗单位
            unit = BattleUnit(
                unit_id=unit_data.get("id", i),
                name=unit_data.get("name", f"Unit_{i}"),
                unit_type=unit_data.get("type", "normal"),
                level=unit_data.get("level", 1),
                attributes=attributes
            )
            
            # 设置队伍和位置
            unit.team_id = team_id
            unit.position = i
            
            # 设置技能
            unit.skills = unit_data.get("skills", [1001])  # 默认普通攻击
            unit.ai_type = unit_data.get("ai_type", "normal")
            
            units.append(unit)
        
        return units
    
    def _calculate_statistics(self, context: BattleContext, rounds_data: List[RoundData]) -> BattleStatistics:
        """计算战斗统计
        
        Args:
            context: 战斗上下文
            rounds_data: 回合数据
            
        Returns:
            BattleStatistics: 战斗统计
        """
        stats = BattleStatistics()
        
        # 基础统计
        stats.total_damage = context.total_damage.copy()
        stats.total_heal = context.total_heal.copy()
        
        # 初始化统计字典
        for unit in context.get_all_units():
            unit_id = unit.id
            stats.kills[unit_id] = 0
            stats.deaths[unit_id] = 1 if unit.is_dead() else 0
            stats.skill_usage[unit_id] = {}
            stats.damage_taken[unit_id] = 0
            stats.heal_received[unit_id] = 0
            stats.max_damage_single[unit_id] = 0
            stats.survival_time[unit_id] = 0
        
        # 分析回合数据
        for round_data in rounds_data:
            for action in round_data.actions:
                attacker_id = action.attacker_id
                skill_id = action.skill_id
                
                # 技能使用次数
                if skill_id not in stats.skill_usage[attacker_id]:
                    stats.skill_usage[attacker_id][skill_id] = 0
                stats.skill_usage[attacker_id][skill_id] += 1
                
                # 伤害和治疗统计
                for i, target_id in enumerate(action.targets):
                    if i < len(action.damages):
                        damage = action.damages[i]
                        stats.damage_taken[target_id] += damage
                        stats.max_damage_single[attacker_id] = max(
                            stats.max_damage_single[attacker_id], damage
                        )
                    
                    if i < len(action.heals):
                        heal = action.heals[i]
                        stats.heal_received[target_id] += heal
        
        # 计算存活时间
        for unit in context.get_all_units():
            unit_id = unit.id
            if unit.is_alive():
                stats.survival_time[unit_id] = len(rounds_data)
            else:
                # 找到死亡回合
                for round_num, round_data in enumerate(rounds_data, 1):
                    if unit_id in round_data.unit_states:
                        unit_state = round_data.unit_states[unit_id]
                        if unit_state.get("state") == UnitState.DEAD.value:
                            stats.survival_time[unit_id] = round_num
                            break
        
        return stats
    
    def _calculate_rewards(self, request: BattleRequest, report: BattleReport) -> Dict[str, Any]:
        """计算奖励
        
        Args:
            request: 战斗请求
            report: 战斗报告
            
        Returns:
            Dict[str, Any]: 奖励数据
        """
        rewards = {
            "exp": 0,
            "gold": 0,
            "items": [],
            "achievement": []
        }
        
        # 基础奖励
        if report.winner == 1:  # 攻击方胜利
            rewards["exp"] = 100
            rewards["gold"] = 50
        elif report.winner == 2:  # 防守方胜利（PVE中通常不会发生）
            rewards["exp"] = 20
            rewards["gold"] = 10
        else:  # 平局
            rewards["exp"] = 10
            rewards["gold"] = 5
        
        # 根据战斗类型调整奖励
        if request.battle_type == BattleType.PVP:
            rewards["exp"] *= 2
            rewards["gold"] *= 2
        elif request.battle_type == BattleType.ARENA:
            rewards["exp"] *= 3
            rewards["gold"] *= 3
        
        # 表现奖励
        if report.statistics:
            # 高伤害奖励
            max_damage = max(report.statistics.total_damage.values()) if report.statistics.total_damage else 0
            if max_damage > 1000:
                rewards["achievement"].append("high_damage")
                rewards["exp"] += 50
        
        return rewards
    
    async def batch_process_battles(self, requests: List[BattleRequest]) -> List[BattleReport]:
        """批量处理战斗
        
        Args:
            requests: 战斗请求列表
            
        Returns:
            List[BattleReport]: 战斗报告列表
        """
        # 创建异步任务
        tasks = [self.process_battle(request) for request in requests]
        
        # 并发执行
        reports = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        final_reports = []
        for i, result in enumerate(reports):
            if isinstance(result, Exception):
                # 创建错误报告
                error_report = BattleReport(
                    battle_id=requests[i].battle_id,
                    battle_type=requests[i].battle_type,
                    status=BattleStatus.ERROR,
                    error_message=str(result)
                )
                final_reports.append(error_report)
            else:
                final_reports.append(result)
        
        return final_reports
    
    def get_battle_report(self, battle_id: str) -> Optional[BattleReport]:
        """获取战斗报告
        
        Args:
            battle_id: 战斗ID
            
        Returns:
            Optional[BattleReport]: 战斗报告
        """
        return self.cache.get(battle_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理器统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = self.stats.copy()
        stats["cache_stats"] = self.cache.get_stats()
        stats["engine_stats"] = self.battle_engine.get_stats()
        return stats
    
    def clear_cache(self) -> None:
        """清理缓存"""
        self.cache.clear()
        self.battle_engine.clear_cache()
    
    def shutdown(self) -> None:
        """关闭处理器"""
        self.io_executor.shutdown(wait=True)
        self.cpu_executor.shutdown(wait=True)
        self.battle_engine.shutdown()