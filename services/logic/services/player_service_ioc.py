"""
玩家服务
Player Service with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 使用自动装载和依赖注入的玩家业务服务
"""

from typing import Dict, Any, Optional
import logging
import time

from common.ioc import service, autowired
from ..services.base.base_logic_service import BaseLogicService

logger = logging.getLogger(__name__)


@service("PlayerService")
class PlayerService(BaseLogicService):
    """
    玩家服务 - 自动装载
    
    处理玩家相关的业务逻辑，包括：
    - 玩家信息管理
    - 资源管理（钻石、金币、体力）
    - 等级经验系统
    - 登录奖励等
    """
    
    @autowired("PlayerRepository")
    def player_repository(self):
        """玩家数据仓库 - 自动注入"""
        pass
    
    # 预留其他服务依赖
    # @autowired("ItemService")
    # def item_service(self):
    #     """道具服务 - 自动注入"""
    #     pass
    
    # @autowired("TaskService")
    # def task_service(self):
    #     """任务服务 - 自动注入"""
    #     pass
    
    async def on_initialize(self) -> None:
        """服务初始化"""
        await super().on_initialize()
        self.logger.info("PlayerService initialized")
        
        # 预加载玩家配置
        await self._load_player_config()
    
    async def _load_player_config(self) -> None:
        """加载玩家相关配置"""
        # 这里可以从配置管理器加载配置
        self._config_cache.update({
            "max_energy": 100,
            "energy_recover_interval": 300,  # 5分钟恢复1点体力
            "daily_login_reward": 100,
            "level_up_gold_reward": 50
        })
    
    async def get_player_info(self, player_id: str) -> Dict[str, Any]:
        """
        获取玩家信息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家信息字典
        """
        try:
            # 1. 参数验证
            validation_result = await self.validate_player_action(player_id, "get_info")
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 2. 调用Repository获取数据
            player_data = await self.player_repository.get_player(player_id)
            
            # 3. 业务处理
            if not player_data:
                return self.error_response("Player not found")
            
            # 4. 格式化返回数据
            response_data = {
                "player_id": player_data["player_id"],
                "nickname": player_data.get("nickname", ""),
                "level": player_data.get("level", 1),
                "exp": player_data.get("exp", 0),
                "diamond": player_data.get("diamond", 0),
                "gold": player_data.get("gold", 0),
                "energy": player_data.get("energy", 0),
                "vip_level": player_data.get("vip_level", 0),
                "online_status": player_data.get("online_status", False),
                "last_login": player_data.get("last_login")
            }
            
            return self.success_response(response_data)
            
        except Exception as e:
            self.logger.error(f"Error getting player info for {player_id}: {e}")
            return self.error_response(f"Failed to get player info: {e}")
    
    async def get_or_create_player(
        self,
        player_id: str,
        nickname: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        获取或创建玩家
        
        Args:
            player_id: 玩家ID
            nickname: 昵称
            **kwargs: 其他创建参数
            
        Returns:
            玩家信息或创建结果
        """
        try:
            # 1. 先尝试获取现有玩家
            player_data = await self.player_repository.get_player(player_id)
            if player_data:
                return self.success_response(player_data, "Player found")
            
            # 2. 玩家不存在，创建新玩家
            create_data = {
                "nickname": nickname or f"Player{player_id[-6:]}",
                **kwargs
            }
            
            result = await self.player_repository.create_player(player_id, create_data)
            
            if result.get("success"):
                # 获取创建后的完整数据
                new_player_data = await self.player_repository.get_player(player_id)
                
                # 记录业务日志
                await self.log_business_action(
                    player_id, "create_player", create_data, result
                )
                
                return self.success_response(new_player_data, "Player created")
            else:
                return self.error_response("Failed to create player")
            
        except Exception as e:
            self.logger.error(f"Error getting or creating player {player_id}: {e}")
            return self.error_response(f"Failed to get or create player: {e}")
    
    async def add_diamond(
        self,
        player_id: str,
        amount: int,
        source: str,
        order_id: str = None
    ) -> Dict[str, Any]:
        """
        增加钻石
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            order_id: 订单ID（可选，用于幂等性检查）
            
        Returns:
            操作结果
        """
        try:
            # 1. 业务验证
            if amount <= 0:
                return self.error_response("Invalid amount")
            
            validation_result = await self.validate_player_action(
                player_id, "add_diamond", amount=amount
            )
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 2. 幂等性检查（如果有订单ID）
            if order_id:
                if await self._check_order_processed(order_id):
                    return self.error_response("Order already processed")
                await self._mark_order_processed(order_id)
            
            # 3. 调用Repository更新数据
            result = await self.player_repository.update_diamond(player_id, amount)
            
            # 4. 触发相关业务
            if result.get("success"):
                # 发送事件
                await self.emit_event("diamond_changed", {
                    "player_id": player_id,
                    "amount": amount,
                    "source": source,
                    "new_value": result.get("new_value", 0)
                })
                
                # 检查任务进度（如果有任务服务）
                # await self.task_service.check_diamond_tasks(player_id, amount)
                
                # 记录业务日志
                await self.log_business_action(
                    player_id, "add_diamond", 
                    {"amount": amount, "source": source}, result
                )
            
            return self.success_response(result) if result.get("success") else self.error_response("Failed to add diamond")
            
        except Exception as e:
            self.logger.error(f"Error adding diamond for {player_id}: {e}")
            return self.error_response(f"Failed to add diamond: {e}")
    
    async def consume_diamond(
        self,
        player_id: str,
        amount: int,
        source: str
    ) -> Dict[str, Any]:
        """
        消耗钻石
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            
        Returns:
            操作结果
        """
        try:
            # 1. 业务验证
            if amount <= 0:
                return self.error_response("Invalid amount")
            
            validation_result = await self.validate_player_action(
                player_id, "consume_diamond", amount=amount
            )
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 2. 调用Repository更新数据（使用负数）
            result = await self.player_repository.update_diamond(player_id, -amount)
            
            # 3. 处理结果
            if result.get("success"):
                # 发送事件
                await self.emit_event("diamond_consumed", {
                    "player_id": player_id,
                    "amount": amount,
                    "source": source,
                    "new_value": result.get("new_value", 0)
                })
                
                # 记录业务日志
                await self.log_business_action(
                    player_id, "consume_diamond",
                    {"amount": amount, "source": source}, result
                )
            
            return self.success_response(result) if result.get("success") else self.error_response(result.get("error", "Insufficient diamond"))
            
        except Exception as e:
            self.logger.error(f"Error consuming diamond for {player_id}: {e}")
            return self.error_response(f"Failed to consume diamond: {e}")
    
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
        try:
            if exp <= 0:
                return self.error_response("Invalid experience amount")
            
            # 1. 获取当前玩家数据
            player_data = await self.player_repository.get_player(player_id)
            if not player_data:
                return self.error_response("Player not found")
            
            current_level = player_data.get("level", 1)
            current_exp = player_data.get("exp", 0)
            
            # 2. 计算升级
            new_exp = current_exp + exp
            level_up_count = 0
            new_level = current_level
            remaining_exp = new_exp
            
            # 简单的升级公式：每级需要 level * 100 经验
            while True:
                exp_needed = new_level * 100
                if remaining_exp >= exp_needed:
                    remaining_exp -= exp_needed
                    new_level += 1
                    level_up_count += 1
                else:
                    break
            
            # 3. 更新玩家数据
            if level_up_count > 0:
                # 升级了，更新等级和经验
                await self.player_repository.update_level(new_level, remaining_exp)
                
                # 升级奖励
                level_reward = level_up_count * self.get_config("level_up_gold_reward", 50)
                await self.player_repository.update_gold(player_id, level_reward)
                
                self.logger.info(f"Player {player_id} level up: {current_level} -> {new_level}")
                
                # 发送升级事件
                await self.emit_event("player_level_up", {
                    "player_id": player_id,
                    "old_level": current_level,
                    "new_level": new_level,
                    "level_reward": level_reward
                })
            else:
                # 没有升级，只更新经验
                await self.player_repository.update_player(player_id, {"exp": new_exp})
            
            result = {
                "success": True,
                "exp_added": exp,
                "level_up": level_up_count > 0,
                "old_level": current_level,
                "new_level": new_level,
                "level_reward": level_up_count * self.get_config("level_up_gold_reward", 50) if level_up_count > 0 else 0
            }
            
            # 记录业务日志
            await self.log_business_action(
                player_id, "add_experience",
                {"exp": exp, "source": source}, result
            )
            
            return self.success_response(result)
            
        except Exception as e:
            self.logger.error(f"Error adding experience for {player_id}: {e}")
            return self.error_response(f"Failed to add experience: {e}")
    
    async def update_login_info(self, player_id: str) -> Dict[str, Any]:
        """
        更新登录信息并处理每日奖励
        
        Args:
            player_id: 玩家ID
            
        Returns:
            更新结果
        """
        try:
            # 1. 获取玩家信息
            player_data = await self.player_repository.get_player(player_id)
            if not player_data:
                return self.error_response("Player not found")
            
            current_time = time.time()
            last_login = player_data.get("last_login")
            
            # 2. 检查是否今日首次登录
            is_daily_first = True
            login_reward = 0
            
            if last_login:
                last_login_time = float(last_login) if isinstance(last_login, (int, float, str)) else time.time()
                today = time.strftime('%Y-%m-%d', time.localtime(current_time))
                last_day = time.strftime('%Y-%m-%d', time.localtime(last_login_time))
                is_daily_first = today != last_day
            
            # 3. 更新登录状态
            await self.player_repository.set_online_status(player_id, True)
            
            # 4. 每日首次登录奖励
            if is_daily_first:
                login_reward = self.get_config("daily_login_reward", 100)
                await self.player_repository.update_gold(player_id, login_reward)
                
                self.logger.info(f"Player {player_id} daily login reward: {login_reward}")
                
                # 发送每日登录事件
                await self.emit_event("daily_login", {
                    "player_id": player_id,
                    "reward": login_reward
                })
            
            result = {
                "success": True,
                "is_daily_first": is_daily_first,
                "login_reward": login_reward,
                "login_time": current_time
            }
            
            # 记录业务日志
            await self.log_business_action(player_id, "update_login", {}, result)
            
            return self.success_response(result)
            
        except Exception as e:
            self.logger.error(f"Error updating login info for {player_id}: {e}")
            return self.error_response(f"Failed to update login info: {e}")
    
    async def recover_energy(self, player_id: str) -> Dict[str, Any]:
        """
        恢复体力（基于时间）
        
        Args:
            player_id: 玩家ID
            
        Returns:
            恢复结果
        """
        try:
            player_data = await self.player_repository.get_player(player_id)
            if not player_data:
                return self.error_response("Player not found")
            
            current_energy = player_data.get("energy", 0)
            max_energy = self.get_config("max_energy", 100)
            
            if current_energy >= max_energy:
                return self.success_response({
                    "energy_recovered": 0,
                    "current_energy": current_energy
                })
            
            # 计算恢复的体力
            last_activity = player_data.get("last_activity", time.time())
            current_time = time.time()
            time_passed = int(current_time - last_activity)
            
            energy_recover_interval = self.get_config("energy_recover_interval", 300)
            energy_recovered = min(
                time_passed // energy_recover_interval,
                max_energy - current_energy
            )
            
            if energy_recovered > 0:
                result = await self.player_repository.update_energy(player_id, energy_recovered)
                
                if result.get("success"):
                    return self.success_response({
                        "energy_recovered": energy_recovered,
                        "current_energy": result.get("new_value", current_energy)
                    })
            
            return self.success_response({
                "energy_recovered": 0,
                "current_energy": current_energy
            })
            
        except Exception as e:
            self.logger.error(f"Error recovering energy for {player_id}: {e}")
            return self.error_response(f"Failed to recover energy: {e}")
    
    async def set_offline(self, player_id: str) -> Dict[str, Any]:
        """
        设置玩家离线
        
        Args:
            player_id: 玩家ID
            
        Returns:
            操作结果
        """
        try:
            result = await self.player_repository.set_online_status(player_id, False)
            
            if result.get("success"):
                # 发送离线事件
                await self.emit_event("player_offline", {"player_id": player_id})
                
                return self.success_response("Player set offline")
            else:
                return self.error_response("Failed to set player offline")
            
        except Exception as e:
            self.logger.error(f"Error setting player offline {player_id}: {e}")
            return self.error_response(f"Failed to set offline: {e}")
    
    async def _check_order_processed(self, order_id: str) -> bool:
        """
        检查订单是否已处理（幂等性检查）
        
        Args:
            order_id: 订单ID
            
        Returns:
            是否已处理
        """
        # 这里应该通过Redis或数据库检查订单状态
        # 暂时返回False，实际项目中需要实现
        return False
    
    async def _mark_order_processed(self, order_id: str) -> None:
        """
        标记订单已处理
        
        Args:
            order_id: 订单ID
        """
        # 这里应该记录订单处理状态到Redis或数据库
        # 暂时空实现，实际项目中需要实现
        pass