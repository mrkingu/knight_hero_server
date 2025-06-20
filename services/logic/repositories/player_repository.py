"""
玩家数据仓库
Player Repository with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 继承BaseIoCRepository，提供玩家数据的CRUD操作，支持自动装载
"""

from typing import Dict, Any, Optional
import logging

from common.ioc import repository
from common.database.repository.enhanced_base_repository import BaseIoCRepository

logger = logging.getLogger(__name__)


@repository("PlayerRepository")
class PlayerRepository(BaseIoCRepository):
    """
    玩家数据仓库
    
    负责玩家数据的存储、缓存和原子操作
    """
    
    def __init__(self):
        """初始化玩家仓库"""
        super().__init__("players")
    
    async def on_initialize(self) -> None:
        """初始化仓库"""
        await super().on_initialize()
        self.logger.info("PlayerRepository initialized")
    
    async def get_player(self, player_id: str) -> Optional[dict]:
        """
        获取玩家数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家数据字典
        """
        try:
            player_data = await self.get_by_id(player_id)
            if player_data:
                self.logger.debug(f"Retrieved player data for {player_id}")
            return player_data
            
        except Exception as e:
            self.logger.error(f"Error getting player {player_id}: {e}")
            raise
    
    async def create_player(self, player_id: str, player_data: dict) -> dict:
        """
        创建新玩家
        
        Args:
            player_id: 玩家ID
            player_data: 玩家数据
            
        Returns:
            创建结果
        """
        try:
            # 添加默认字段
            default_data = {
                "player_id": player_id,
                "level": 1,
                "exp": 0,
                "diamond": 0,
                "gold": 1000,
                "energy": 100,
                "vip_level": 0,
                "vip_exp": 0,
                "online_status": False,
                "created_at": __import__('time').time(),
                "last_login": None
            }
            
            # 合并用户提供的数据
            final_data = {**default_data, **player_data}
            
            result = await self.create(player_id, final_data)
            
            if result.get("success"):
                self.logger.info(f"Created new player: {player_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error creating player {player_id}: {e}")
            raise
    
    async def update_player(self, player_id: str, update_data: dict) -> dict:
        """
        更新玩家数据
        
        Args:
            player_id: 玩家ID
            update_data: 更新数据
            
        Returns:
            更新结果
        """
        try:
            # 添加更新时间戳
            update_data_with_timestamp = dict(update_data)
            update_data_with_timestamp["updated_at"] = __import__('time').time()
            
            result = await self.update(player_id, update_data_with_timestamp)
            
            if result.get("success"):
                self.logger.debug(f"Updated player {player_id}: {list(update_data.keys())}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating player {player_id}: {e}")
            raise
    
    async def update_diamond(self, player_id: str, amount: int) -> dict:
        """
        更新钻石数量（原子操作）
        
        Args:
            player_id: 玩家ID
            amount: 变化数量（可以是负数）
            
        Returns:
            操作结果
        """
        try:
            if amount > 0:
                # 增加钻石
                result = await self.increment(player_id, "diamond", amount, "diamond_add")
            else:
                # 减少钻石（需要检查余额）
                result = await self.decrement_with_check(
                    player_id, "diamond", abs(amount), "diamond_consume", min_value=0
                )
            
            if result.get("success"):
                self.logger.info(f"Updated diamond for {player_id}: {amount}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating diamond for {player_id}: {e}")
            raise
    
    async def update_gold(self, player_id: str, amount: int) -> dict:
        """
        更新金币数量（原子操作）
        
        Args:
            player_id: 玩家ID
            amount: 变化数量（可以是负数）
            
        Returns:
            操作结果
        """
        try:
            if amount > 0:
                # 增加金币
                result = await self.increment(player_id, "gold", amount, "gold_add")
            else:
                # 减少金币（需要检查余额）
                result = await self.decrement_with_check(
                    player_id, "gold", abs(amount), "gold_consume", min_value=0
                )
            
            if result.get("success"):
                self.logger.info(f"Updated gold for {player_id}: {amount}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating gold for {player_id}: {e}")
            raise
    
    async def update_level(self, player_id: str, new_level: int, new_exp: int = 0) -> dict:
        """
        更新玩家等级
        
        Args:
            player_id: 玩家ID
            new_level: 新等级
            new_exp: 新经验值
            
        Returns:
            更新结果
        """
        try:
            update_data = {
                "level": new_level,
                "exp": new_exp,
                "level_updated_at": __import__('time').time()
            }
            
            result = await self.update_player(player_id, update_data)
            
            if result.get("success"):
                self.logger.info(f"Updated level for {player_id}: {new_level}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating level for {player_id}: {e}")
            raise
    
    async def update_energy(self, player_id: str, amount: int) -> dict:
        """
        更新体力值（原子操作）
        
        Args:
            player_id: 玩家ID
            amount: 变化数量（可以是负数）
            
        Returns:
            操作结果
        """
        try:
            if amount > 0:
                # 增加体力（但不能超过最大值）
                current_data = await self.get_player(player_id)
                if not current_data:
                    return {"success": False, "error": "Player not found"}
                
                current_energy = current_data.get("energy", 0)
                max_energy = 100  # 可以从配置获取
                
                if current_energy >= max_energy:
                    return {
                        "success": True,
                        "message": "Energy already at maximum",
                        "current_energy": current_energy
                    }
                
                # 计算实际增加的体力
                actual_amount = min(amount, max_energy - current_energy)
                result = await self.increment(player_id, "energy", actual_amount, "energy_recover")
            else:
                # 减少体力（需要检查余额）
                result = await self.decrement_with_check(
                    player_id, "energy", abs(amount), "energy_consume", min_value=0
                )
            
            if result.get("success"):
                self.logger.debug(f"Updated energy for {player_id}: {amount}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating energy for {player_id}: {e}")
            raise
    
    async def set_online_status(self, player_id: str, online: bool) -> dict:
        """
        设置玩家在线状态
        
        Args:
            player_id: 玩家ID
            online: 是否在线
            
        Returns:
            更新结果
        """
        try:
            update_data = {
                "online_status": online,
                "last_activity": __import__('time').time()
            }
            
            if online:
                update_data["last_login"] = __import__('time').time()
            
            result = await self.update_player(player_id, update_data)
            
            if result.get("success"):
                status = "online" if online else "offline"
                self.logger.debug(f"Set player {player_id} status to {status}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error setting online status for {player_id}: {e}")
            raise
    
    async def get_player_summary(self, player_id: str) -> Optional[dict]:
        """
        获取玩家摘要信息（用于排行榜等）
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家摘要信息
        """
        try:
            player_data = await self.get_player(player_id)
            if not player_data:
                return None
            
            summary = {
                "player_id": player_id,
                "nickname": player_data.get("nickname", ""),
                "level": player_data.get("level", 1),
                "vip_level": player_data.get("vip_level", 0),
                "online_status": player_data.get("online_status", False),
                "last_login": player_data.get("last_login")
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting player summary for {player_id}: {e}")
            return None
    
    async def check_player_exists(self, player_id: str) -> bool:
        """
        检查玩家是否存在
        
        Args:
            player_id: 玩家ID
            
        Returns:
            是否存在
        """
        try:
            player_data = await self.get_player(player_id)
            return player_data is not None
            
        except Exception as e:
            self.logger.error(f"Error checking player existence for {player_id}: {e}")
            return False