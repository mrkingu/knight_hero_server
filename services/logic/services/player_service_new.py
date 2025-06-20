"""
重构后的玩家服务
封装所有玩家相关的业务逻辑和数据访问
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from datetime import datetime
import time
import logging

from common.database.repository import get_repository_manager
from common.utils import validate_data, Validator, ErrorHandler

logger = logging.getLogger(__name__)

class PlayerServiceNew:
    """
    玩家服务 - 外部访问玩家数据的唯一入口
    不再继承Repository，而是通过RepositoryManager访问
    """
    
    def __init__(self):
        # 通过RepositoryManager获取Repository
        self._repo_manager = get_repository_manager()
        self._error_handler = ErrorHandler(logger)
        
        # 业务配置
        self.max_energy = 100
        self.energy_recover_interval = 300  # 秒
        self.daily_login_reward = 100
    
    def _get_player_repo(self):
        """获取玩家Repository"""
        return self._repo_manager.get_repository("player")
    
    async def get_player_info(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家信息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家信息字典
        """
        try:
            # 验证输入
            validate_data({"player_id": player_id}, {
                "player_id": [Validator.required, Validator.player_id_format]
            })
            
            # 通过Repository获取数据
            repo = self._get_player_repo()
            player_data = await repo.get(player_id)
            
            if not player_data:
                return None
            
            # 返回需要的字段，隐藏内部实现
            return {
                "player_id": player_data.get("player_id"),
                "nickname": player_data.get("nickname"),
                "level": player_data.get("level"),
                "vip_level": player_data.get("vip_level"),
                "diamond": player_data.get("diamond"),
                "gold": player_data.get("gold"),
                "energy": player_data.get("energy"),
                "online_status": player_data.get("online_status"),
                "last_login": player_data.get("last_login")
            }
            
        except Exception as e:
            self._error_handler.handle_error(e, {"method": "get_player_info", "player_id": player_id})
            return None
    
    async def add_diamond(
        self, 
        player_id: str, 
        amount: int, 
        source: str,
        reason: str,
        order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        增加玩家钻石
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            reason: 原因
            order_id: 订单ID（可选）
            
        Returns:
            操作结果
        """
        try:
            # 业务验证
            if amount <= 0:
                return {"success": False, "reason": "invalid_amount"}
            
            validate_data({"player_id": player_id}, {
                "player_id": [Validator.required, Validator.player_id_format]
            })
            
            # 调用Repository
            repo = self._get_player_repo()
            result = await repo.modify_field(
                entity_id=player_id,
                field="diamond",
                operation="increment",
                value=amount,
                source=f"{source}:{reason}"
            )
            
            # 可能的额外业务逻辑
            if result.get("success"):
                # 发送事件通知
                await self._emit_diamond_change_event(player_id, amount, source)
                logger.info(f"玩家 {player_id} 获得钻石: {amount} (来源: {source})")
            
            return result
            
        except Exception as e:
            self._error_handler.handle_error(e, {
                "method": "add_diamond", 
                "player_id": player_id, 
                "amount": amount,
                "source": source
            })
            return {"success": False, "reason": "system_error"}
    
    async def consume_diamond(
        self,
        player_id: str,
        amount: int,
        source: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        消耗玩家钻石
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            reason: 原因
            
        Returns:
            操作结果
        """
        try:
            # 业务验证
            if amount <= 0:
                return {"success": False, "reason": "invalid_amount"}
            
            validate_data({"player_id": player_id}, {
                "player_id": [Validator.required, Validator.player_id_format]
            })
            
            # 先检查余额
            player_info = await self.get_player_info(player_id)
            if not player_info:
                return {"success": False, "reason": "player_not_found"}
            
            if player_info["diamond"] < amount:
                return {"success": False, "reason": "insufficient_diamond"}
            
            # 调用Repository
            repo = self._get_player_repo()
            result = await repo.modify_field(
                entity_id=player_id,
                field="diamond",
                operation="decrement",
                value=amount,
                source=f"{source}:{reason}"
            )
            
            if result.get("success"):
                logger.info(f"玩家 {player_id} 消耗钻石: {amount} (来源: {source})")
            
            return result
            
        except Exception as e:
            self._error_handler.handle_error(e, {
                "method": "consume_diamond",
                "player_id": player_id,
                "amount": amount,
                "source": source
            })
            return {"success": False, "reason": "system_error"}
    
    async def add_gold(
        self,
        player_id: str,
        amount: int,
        source: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        增加玩家金币
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            reason: 原因
            
        Returns:
            操作结果
        """
        try:
            if amount <= 0:
                return {"success": False, "reason": "invalid_amount"}
            
            validate_data({"player_id": player_id}, {
                "player_id": [Validator.required, Validator.player_id_format]
            })
            
            repo = self._get_player_repo()
            result = await repo.modify_field(
                entity_id=player_id,
                field="gold",
                operation="increment",
                value=amount,
                source=f"{source}:{reason}" if reason else source
            )
            
            if result.get("success"):
                logger.info(f"玩家 {player_id} 获得金币: {amount} (来源: {source})")
            
            return result
            
        except Exception as e:
            self._error_handler.handle_error(e, {
                "method": "add_gold",
                "player_id": player_id,
                "amount": amount,
                "source": source
            })
            return {"success": False, "reason": "system_error"}
    
    async def create_player(
        self,
        player_id: str,
        nickname: str,
        **extra_params
    ) -> Dict[str, Any]:
        """
        创建新玩家
        
        Args:
            player_id: 玩家ID
            nickname: 昵称
            **extra_params: 额外参数
            
        Returns:
            创建结果
        """
        try:
            # 验证输入
            validate_data({
                "player_id": player_id,
                "nickname": nickname
            }, {
                "player_id": [Validator.required, Validator.player_id_format],
                "nickname": [Validator.required, lambda v, f: Validator.string_length(v, 1, 50, f)]
            })
            
            # 检查玩家是否已存在
            if await self.get_player_info(player_id):
                return {"success": False, "reason": "player_already_exists"}
            
            # 创建玩家数据
            player_data = {
                "player_id": player_id,
                "nickname": nickname,
                "level": 1,
                "exp": 0,
                "diamond": 0,
                "gold": 1000,  # 初始金币
                "energy": self.max_energy,
                "vip_level": 0,
                "vip_exp": 0,
                "last_login": datetime.now().isoformat(),
                "online_status": True,
                "created_at": datetime.now().isoformat()
            }
            
            # 添加额外参数
            player_data.update(extra_params)
            
            # 保存到Repository
            repo = self._get_player_repo()
            success = await repo.save(player_id, player_data)
            
            if success:
                logger.info(f"创建新玩家: {player_id} ({nickname})")
                return {"success": True, "player_data": player_data}
            else:
                return {"success": False, "reason": "create_failed"}
                
        except Exception as e:
            self._error_handler.handle_error(e, {
                "method": "create_player",
                "player_id": player_id,
                "nickname": nickname
            })
            return {"success": False, "reason": "system_error"}
    
    async def _emit_diamond_change_event(self, player_id: str, amount: int, source: str):
        """发送钻石变化事件"""
        # 这里可以发送到消息队列或事件总线
        # 简化实现，只记录日志
        logger.info(f"钻石变化事件: 玩家={player_id}, 数量={amount}, 来源={source}")
    
    async def get_player_summary(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家摘要信息（用于排行榜等）
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家摘要信息
        """
        try:
            player_info = await self.get_player_info(player_id)
            if not player_info:
                return None
            
            return {
                "player_id": player_id,
                "nickname": player_info["nickname"],
                "level": player_info["level"],
                "vip_level": player_info["vip_level"],
                "online_status": player_info["online_status"]
            }
            
        except Exception as e:
            self._error_handler.handle_error(e, {"method": "get_player_summary", "player_id": player_id})
            return None

# 为了向后兼容，保留原有的PlayerService接口
PlayerService = PlayerServiceNew