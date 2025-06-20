"""
玩家数据Repository - 自动处理并发
业务层可以直接调用，不需要关心并发问题
作者: lx
日期: 2025-06-18
"""
import asyncio
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..base_repository import BaseRepository
from ..concurrent_operations import OperationType
from ..models import Player
from ..redis_cache import RedisCache
from ..mongo_client import MongoClient


class PlayerRepository(BaseRepository):
    """
    玩家数据仓库
    所有方法都是并发安全的
    """
    
    def __init__(self, redis_client: RedisCache, mongo_client: MongoClient):
        super().__init__(
            redis_client=redis_client,
            mongo_client=mongo_client,
            collection_name="players",
            document_class=Player,
            cache_ttl=300  # 玩家数据缓存5分钟
        )
    
    async def create_player(
        self,
        player_id: str,
        nickname: str,
        device_id: Optional[str] = None,
        platform: Optional[str] = None
    ) -> Optional[Player]:
        """
        创建新玩家
        
        Args:
            player_id: 玩家ID
            nickname: 昵称
            device_id: 设备ID
            platform: 平台
            
        Returns:
            创建的玩家对象或None
        """
        try:
            # 检查玩家是否已存在
            existing_player = await self.get(player_id)
            if existing_player:
                return existing_player
            
            player_data = {
                "player_id": player_id,
                "nickname": nickname,
                "level": 1,
                "exp": 0,
                "vip_level": 0,
                "vip_exp": 0,
                "diamond": 0,
                "gold": 1000,  # 新手赠送1000金币
                "energy": 100,
                "items": {},
                "current_stage": 1,
                "max_stage": 1,
                "device_id": device_id,
                "platform": platform,
                "create_time": datetime.now(),
                "last_login": datetime.now(),
                "last_save": datetime.now()
            }
            
            return await self.create(player_data)
            
        except Exception as e:
            self.logger.error(f"创建玩家失败: {player_id}, {e}")
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
        添加钻石(并发安全)
        支持支付回调、活动奖励、GM发放等各种场景
        
        Args:
            player_id: 玩家ID
            amount: 钻石数量
            source: 来源(payment/activity/gm/schedule等)
            reason: 原因说明
            order_id: 订单ID(用于支付场景的幂等性)
            
        Returns:
            操作结果
        """
        # 如果是支付订单，检查幂等性
        if order_id:
            if await self._check_order_processed(order_id):
                return {
                    "success": False,
                    "reason": "order_already_processed",
                    "order_id": order_id
                }
            await self._mark_order_processed(order_id)
        
        return await self.increment(
            entity_id=player_id,
            field="diamond",
            value=amount,
            source=source,
            reason=reason,
            metadata={"order_id": order_id} if order_id else None
        )
    
    async def consume_diamond(
        self, 
        player_id: str, 
        amount: int, 
        source: str, 
        reason: str
    ) -> Dict[str, Any]:
        """
        消耗钻石(并发安全)
        会自动检查余额是否足够
        """
        return await self.decrement_with_check(
            entity_id=player_id,
            field="diamond",
            value=amount,
            source=source,
            reason=reason
        )
    
    async def add_gold(
        self,
        player_id: str,
        amount: int,
        source: str,
        reason: str
    ) -> Dict[str, Any]:
        """添加金币(并发安全)"""
        return await self.increment(
            entity_id=player_id,
            field="gold",
            value=amount,
            source=source,
            reason=reason
        )
    
    async def consume_gold(
        self,
        player_id: str,
        amount: int,
        source: str,
        reason: str
    ) -> Dict[str, Any]:
        """消耗金币(并发安全)"""
        return await self.decrement_with_check(
            entity_id=player_id,
            field="gold",
            value=amount,
            source=source,
            reason=reason
        )
    
    async def add_exp(
        self,
        player_id: str,
        amount: int,
        source: str = "game",
        reason: str = "exp_gain"
    ) -> Dict[str, Any]:
        """
        添加经验值(并发安全)
        会自动处理升级逻辑
        """
        result = await self.increment(
            entity_id=player_id,
            field="exp",
            value=amount,
            source=source,
            reason=reason
        )
        
        if result.get("success"):
            # 异步检查是否需要升级
            asyncio.create_task(self._check_level_up(player_id))
        
        return result
    
    async def add_vip_exp(
        self,
        player_id: str,
        amount: int,
        source: str = "payment",
        reason: str = "vip_exp_gain"
    ) -> Dict[str, Any]:
        """
        添加VIP经验(并发安全)
        会自动处理VIP升级逻辑
        """
        result = await self.increment(
            entity_id=player_id,
            field="vip_exp",
            value=amount,
            source=source,
            reason=reason
        )
        
        if result.get("success"):
            # 异步检查是否需要VIP升级
            asyncio.create_task(self._check_vip_level_up(player_id))
        
        return result
    
    async def set_energy(
        self,
        player_id: str,
        amount: int,
        source: str = "system",
        reason: str = "energy_set"
    ) -> Dict[str, Any]:
        """设置体力值(并发安全)"""
        return await self.set_field(
            entity_id=player_id,
            field="energy",
            value=amount,
            source=source,
            reason=reason
        )
    
    async def consume_energy(
        self,
        player_id: str,
        amount: int,
        source: str = "game",
        reason: str = "energy_consume"
    ) -> Dict[str, Any]:
        """消耗体力(并发安全)"""
        return await self.decrement_with_check(
            entity_id=player_id,
            field="energy",
            value=amount,
            source=source,
            reason=reason
        )
    
    async def add_item(
        self,
        player_id: str,
        item_id: str,
        quantity: int,
        source: str = "game",
        reason: str = "item_reward"
    ) -> Dict[str, Any]:
        """
        添加道具(并发安全)
        
        Args:
            player_id: 玩家ID
            item_id: 道具ID
            quantity: 数量
            source: 来源
            reason: 原因
        """
        # 获取当前背包数据
        player = await self.get(player_id)
        if not player:
            return {
                "success": False,
                "reason": "player_not_found"
            }
        
        current_items = player.items.copy()
        current_quantity = current_items.get(item_id, 0)
        new_quantity = current_quantity + quantity
        current_items[item_id] = new_quantity
        
        return await self.set_field(
            entity_id=player_id,
            field="items",
            value=current_items,
            source=source,
            reason=f"{reason}_{item_id}_{quantity}"
        )
    
    async def consume_item(
        self,
        player_id: str,
        item_id: str,
        quantity: int,
        source: str = "game",
        reason: str = "item_consume"
    ) -> Dict[str, Any]:
        """
        消耗道具(并发安全)
        
        Args:
            player_id: 玩家ID
            item_id: 道具ID
            quantity: 数量
            source: 来源
            reason: 原因
        """
        # 获取当前背包数据
        player = await self.get(player_id)
        if not player:
            return {
                "success": False,
                "reason": "player_not_found"
            }
        
        current_items = player.items.copy()
        current_quantity = current_items.get(item_id, 0)
        
        if current_quantity < quantity:
            return {
                "success": False,
                "reason": "insufficient_item",
                "item_id": item_id,
                "current": current_quantity,
                "required": quantity
            }
        
        new_quantity = current_quantity - quantity
        if new_quantity <= 0:
            current_items.pop(item_id, None)
        else:
            current_items[item_id] = new_quantity
        
        return await self.set_field(
            entity_id=player_id,
            field="items",
            value=current_items,
            source=source,
            reason=f"{reason}_{item_id}_{quantity}"
        )
    
    async def update_stage_progress(
        self,
        player_id: str,
        new_stage: int,
        source: str = "game",
        reason: str = "stage_progress"
    ) -> Dict[str, Any]:
        """
        更新关卡进度(并发安全)
        
        Args:
            player_id: 玩家ID
            new_stage: 新关卡
            source: 来源
            reason: 原因
        """
        operations = [
            {
                "field": "current_stage",
                "operation": OperationType.SET,
                "value": new_stage
            }
        ]
        
        # 如果新关卡比最高关卡高，同时更新最高关卡
        player = await self.get(player_id)
        if player and new_stage > player.max_stage:
            operations.append({
                "field": "max_stage",
                "operation": OperationType.SET,
                "value": new_stage
            })
        
        return await self.batch_modify(
            entity_id=player_id,
            operations=operations,
            source=source,
            reason=reason
        )
    
    async def batch_add_rewards(
        self, 
        player_id: str, 
        rewards: Dict[str, int], 
        source: str,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量添加奖励(并发安全)
        用于定时任务、活动奖励等批量发放场景
        
        Args:
            player_id: 玩家ID
            rewards: 奖励内容 {"diamond": 100, "gold": 1000}
            source: 来源
            task_id: 任务ID(用于定时任务的幂等性)
        """
        # 如果是定时任务，检查是否已发放
        if task_id:
            if await self._check_task_rewarded(player_id, task_id):
                return {
                    "success": False,
                    "reason": "task_already_rewarded",
                    "task_id": task_id
                }
            await self._mark_task_rewarded(player_id, task_id)
        
        # 构建批量操作
        operations = []
        for resource, amount in rewards.items():
            if resource in self.concurrent_fields:
                operations.append({
                    "field": resource,
                    "operation": OperationType.INCREMENT,
                    "value": amount
                })
        
        if not operations:
            return {
                "success": False,
                "reason": "no_valid_rewards"
            }
        
        return await self.batch_modify(
            entity_id=player_id,
            operations=operations,
            source=source,
            reason=f"batch_reward_{task_id}" if task_id else "batch_reward"
        )
    
    async def update_last_login(self, player_id: str) -> Dict[str, Any]:
        """更新最后登录时间"""
        return await self.set_field(
            entity_id=player_id,
            field="last_login",
            value=datetime.now(),
            source="system",
            reason="login_update"
        )
    
    async def get_player_ranking(
        self,
        rank_type: str = "level",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取玩家排行榜
        
        Args:
            rank_type: 排行类型 (level, vip_level)
            limit: 限制数量
        """
        try:
            if rank_type == "level":
                sort_field = [("level", -1), ("exp", -1), ("player_id", 1)]
            elif rank_type == "vip_level":
                sort_field = [("vip_level", -1), ("vip_exp", -1), ("player_id", 1)]
            else:
                return []
            
            players = await self.mongo_client.find_many(
                collection_name=self.collection_name,
                sort=sort_field,
                limit=limit,
                projection={
                    "player_id": 1,
                    "nickname": 1,
                    "level": 1,
                    "exp": 1,
                    "vip_level": 1,
                    "vip_exp": 1
                }
            )
            
            # 添加排名
            for idx, player in enumerate(players):
                player["rank"] = idx + 1
            
            return players
            
        except Exception as e:
            self.logger.error(f"获取排行榜失败: {e}")
            return []
    
    async def _check_level_up(self, player_id: str) -> None:
        """检查并处理玩家升级"""
        try:
            player = await self.get(player_id)
            if not player:
                return
            
            # 简单的升级计算：每1000经验升1级
            target_level = player.exp // 1000 + 1
            
            if target_level > player.level:
                await self.set_field(
                    entity_id=player_id,
                    field="level",
                    value=target_level,
                    source="system",
                    reason="auto_level_up"
                )
                
                self.logger.info(f"玩家升级: {player_id}, {player.level} -> {target_level}")
            
        except Exception as e:
            self.logger.error(f"检查升级失败: {player_id}, {e}")
    
    async def _check_vip_level_up(self, player_id: str) -> None:
        """检查并处理VIP升级"""
        try:
            player = await self.get(player_id)
            if not player:
                return
            
            # VIP等级表：V1=100, V2=300, V3=600, V4=1000...
            vip_levels = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500, 5500]
            
            target_vip_level = 0
            for level, required_exp in enumerate(vip_levels):
                if player.vip_exp >= required_exp:
                    target_vip_level = level
                else:
                    break
            
            if target_vip_level > player.vip_level:
                await self.set_field(
                    entity_id=player_id,
                    field="vip_level",
                    value=target_vip_level,
                    source="system",
                    reason="auto_vip_level_up"
                )
                
                self.logger.info(f"VIP升级: {player_id}, V{player.vip_level} -> V{target_vip_level}")
            
        except Exception as e:
            self.logger.error(f"检查VIP升级失败: {player_id}, {e}")
    
    async def get_player_summary(self, player_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家摘要信息(用于排行榜等场景)"""
        try:
            player = await self.get(player_id)
            if not player:
                return None
            
            return {
                "player_id": player.player_id,
                "nickname": player.nickname,
                "level": player.level,
                "exp": player.exp,
                "vip_level": player.vip_level,
                "diamond": player.diamond,
                "gold": player.gold,
                "current_stage": player.current_stage,
                "max_stage": player.max_stage,
                "last_login": player.last_login
            }
            
        except Exception as e:
            self.logger.error(f"获取玩家摘要失败: {player_id}, {e}")
            return None
    
    @property
    def logger(self):
        """获取日志记录器"""
        import logging
        return logging.getLogger(f"{__name__}.PlayerRepository")