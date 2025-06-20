"""
玩家业务逻辑服务
Player Business Logic Service

作者: lx
日期: 2025-06-20
描述: 继承PlayerRepository，提供玩家相关的业务逻辑封装
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import logging
import asyncio

from common.database.repositories.player_repository import PlayerRepository
from common.database.models.player_model import Player, VIPLevel
from common.database.core import RedisClient, MongoClient

logger = logging.getLogger(__name__)


class PlayerService(PlayerRepository):
    """玩家业务逻辑服务"""
    
    def __init__(self, redis_client=None, mongo_client=None):
        """
        初始化玩家服务
        
        Args:
            redis_client: Redis客户端
            mongo_client: MongoDB客户端
        """
        # 使用传入的客户端，如果没有则创建默认配置的客户端
        if redis_client is None:
            redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
            redis_client = RedisClient(redis_config)
        if mongo_client is None:
            mongo_config = {'host': 'localhost', 'port': 27017, 'database': 'knight_hero'}
            mongo_client = MongoClient(mongo_config)
            
        super().__init__(redis_client, mongo_client)
        
        # 业务配置
        self.max_energy = 100  # 最大体力
        self.energy_recover_interval = 300  # 体力恢复间隔(秒)
        self.daily_login_reward = 100  # 每日登录奖励金币
        
    async def get_or_create(self, player_id: str, **kwargs) -> Player:
        """
        获取或创建玩家
        
        Args:
            player_id: 玩家ID
            **kwargs: 创建时的额外参数
            
        Returns:
            玩家对象
        """
        try:
            # 先尝试从缓存获取
            player_data = await self.get_by_id(player_id)
            if player_data:
                return Player(**player_data)
                
            # 不存在则创建新玩家
            new_player_data = {
                "player_id": player_id,
                "nickname": kwargs.get("nickname", f"玩家{player_id[-6:]}"),
                "level": 1,
                "exp": 0,
                "diamond": 0,
                "gold": 1000,  # 初始金币
                "energy": self.max_energy,
                "vip_level": VIPLevel.V0,
                "vip_exp": 0,
                "last_login": datetime.now().isoformat(),
                "online_status": True
            }
            
            # 添加其他参数
            new_player_data.update(kwargs)
            
            # 保存到数据库
            await self.create(player_id, new_player_data)
            
            logger.info(f"创建新玩家: {player_id}")
            return Player(**new_player_data)
            
        except Exception as e:
            logger.error(f"获取或创建玩家失败 {player_id}: {e}")
            raise
    
    async def update_login_info(self, player_id: str) -> Dict[str, Any]:
        """
        更新登录信息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            更新结果
        """
        try:
            current_time = datetime.now()
            
            # 获取玩家信息
            player_data = await self.get_by_id(player_id)
            if not player_data:
                raise ValueError(f"玩家不存在: {player_id}")
            
            # 检查是否今日首次登录
            last_login = player_data.get("last_login")
            is_daily_first = True
            login_reward = 0
            
            if last_login:
                last_login_date = datetime.fromisoformat(last_login).date()
                today = current_time.date()
                is_daily_first = last_login_date < today
            
            # 更新登录信息
            update_data = {
                "last_login": current_time.isoformat(),
                "online_status": True
            }
            
            # 每日首次登录奖励
            if is_daily_first:
                login_reward = self.daily_login_reward
                await self.add_gold(player_id, login_reward, "daily_login")
                logger.info(f"玩家 {player_id} 获得每日登录奖励: {login_reward}金币")
            
            # 更新数据
            await self.update(player_id, update_data)
            
            return {
                "success": True,
                "is_daily_first": is_daily_first,
                "login_reward": login_reward,
                "login_time": current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"更新登录信息失败 {player_id}: {e}")
            raise
    
    async def add_gold(
        self, 
        player_id: str, 
        amount: int, 
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        添加金币
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            
        Returns:
            操作结果
        """
        if amount <= 0:
            raise ValueError("金币数量必须大于0")
            
        return await self.increment(
            entity_id=player_id,
            field="gold",
            value=amount,
            source=source
        )
    
    async def consume_gold(
        self, 
        player_id: str, 
        amount: int, 
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        消耗金币
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            
        Returns:
            操作结果
        """
        if amount <= 0:
            raise ValueError("金币数量必须大于0")
            
        return await self.decrement_with_check(
            entity_id=player_id,
            field="gold",
            value=amount,
            source=source
        )
    
    async def add_experience(
        self, 
        player_id: str, 
        exp: int, 
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        添加经验值（可能升级）
        
        Args:
            player_id: 玩家ID
            exp: 经验值
            source: 来源
            
        Returns:
            操作结果，包含是否升级信息
        """
        if exp <= 0:
            raise ValueError("经验值必须大于0")
        
        try:
            # 添加经验
            result = await self.increment(
                entity_id=player_id,
                field="exp",
                value=exp,
                source=source
            )
            
            # 检查是否需要升级
            player_data = await self.get_by_id(player_id)
            current_level = player_data.get("level", 1)
            current_exp = player_data.get("exp", 0)
            
            # 简单的升级公式：每级需要 level * 100 经验
            level_up_count = 0
            new_level = current_level
            remaining_exp = current_exp
            
            while True:
                exp_needed = new_level * 100
                if remaining_exp >= exp_needed:
                    remaining_exp -= exp_needed
                    new_level += 1
                    level_up_count += 1
                else:
                    break
            
            # 如果升级了，更新等级和经验
            if level_up_count > 0:
                await self.update(player_id, {
                    "level": new_level,
                    "exp": remaining_exp
                })
                
                logger.info(f"玩家 {player_id} 升级: {current_level} -> {new_level}")
                
                # 升级奖励
                level_reward = level_up_count * 50  # 每级奖励50金币
                await self.add_gold(player_id, level_reward, "level_up")
            
            return {
                "success": True,
                "exp_added": exp,
                "level_up": level_up_count > 0,
                "old_level": current_level,
                "new_level": new_level,
                "level_reward": level_up_count * 50 if level_up_count > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"添加经验失败 {player_id}: {e}")
            raise
    
    async def recover_energy(self, player_id: str) -> Dict[str, Any]:
        """
        恢复体力（基于时间）
        
        Args:
            player_id: 玩家ID
            
        Returns:
            恢复结果
        """
        try:
            player_data = await self.get_by_id(player_id)
            if not player_data:
                raise ValueError(f"玩家不存在: {player_id}")
            
            current_energy = player_data.get("energy", 0)
            last_login = player_data.get("last_login")
            
            if current_energy >= self.max_energy:
                return {"success": True, "energy_recovered": 0, "current_energy": current_energy}
            
            # 计算恢复的体力
            now = time.time()
            last_time = time.time()
            
            if last_login:
                last_time = datetime.fromisoformat(last_login).timestamp()
            
            time_passed = int(now - last_time)
            energy_recovered = min(
                time_passed // self.energy_recover_interval,
                self.max_energy - current_energy
            )
            
            if energy_recovered > 0:
                new_energy = min(current_energy + energy_recovered, self.max_energy)
                await self.update(player_id, {"energy": new_energy})
                
                return {
                    "success": True,
                    "energy_recovered": energy_recovered,
                    "current_energy": new_energy
                }
            
            return {
                "success": True,
                "energy_recovered": 0,
                "current_energy": current_energy
            }
            
        except Exception as e:
            logger.error(f"恢复体力失败 {player_id}: {e}")
            raise
    
    async def set_offline(self, player_id: str) -> None:
        """
        设置玩家离线
        
        Args:
            player_id: 玩家ID
        """
        try:
            await self.update(player_id, {
                "online_status": False,
                "last_login": datetime.now().isoformat()
            })
            logger.info(f"玩家 {player_id} 设置为离线")
            
        except Exception as e:
            logger.error(f"设置玩家离线失败 {player_id}: {e}")
            raise
    
    async def get_player_summary(self, player_id: str) -> Dict[str, Any]:
        """
        获取玩家摘要信息（用于排行榜等）
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家摘要信息
        """
        try:
            player_data = await self.get_by_id(player_id)
            if not player_data:
                return None
            
            return {
                "player_id": player_id,
                "nickname": player_data.get("nickname", ""),
                "level": player_data.get("level", 1),
                "vip_level": player_data.get("vip_level", 0),
                "online_status": player_data.get("online_status", False)
            }
            
        except Exception as e:
            logger.error(f"获取玩家摘要失败 {player_id}: {e}")
            return None
    
    async def validate_player_action(
        self, 
        player_id: str, 
        action: str, 
        **params
    ) -> bool:
        """
        验证玩家行为是否合法
        
        Args:
            player_id: 玩家ID
            action: 行为类型
            **params: 行为参数
            
        Returns:
            是否合法
        """
        try:
            player_data = await self.get_by_id(player_id)
            if not player_data:
                return False
            
            # 检查玩家是否在线
            if not player_data.get("online_status", False):
                return False
            
            # 根据不同行为进行验证
            if action == "consume_energy":
                required_energy = params.get("amount", 1)
                current_energy = player_data.get("energy", 0)
                return current_energy >= required_energy
                
            elif action == "consume_gold":
                required_gold = params.get("amount", 0)
                current_gold = player_data.get("gold", 0)
                return current_gold >= required_gold
                
            elif action == "consume_diamond":
                required_diamond = params.get("amount", 0)
                current_diamond = player_data.get("diamond", 0)
                return current_diamond >= required_diamond
            
            return True
            
        except Exception as e:
            logger.error(f"验证玩家行为失败 {player_id} {action}: {e}")
            return False