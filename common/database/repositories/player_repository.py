"""
玩家数据仓库
处理玩家相关的所有数据操作
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from ..repository.base_repository import BaseRepository
from ..concurrent.operation_type import OperationType
from ..models.player_model import PlayerModel

class PlayerRepository(BaseRepository):
    """玩家数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(redis_client, mongo_client, "players")
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """定义支持并发操作的字段"""
        meta = getattr(PlayerModel, 'Meta', None)
        return getattr(meta, 'concurrent_fields', {}) if meta else {}
        
    async def add_diamond(
        self,
        player_id: str,
        amount: int,
        source: str,
        order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        添加钻石（并发安全）
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            order_id: 订单ID（用于幂等性）
            
        Returns:
            操作结果
        """
        # 支付订单幂等性检查
        if order_id:
            order_key = f"order:{order_id}"
            if await self.redis.client.exists(order_key):
                return {"success": False, "reason": "duplicate_order"}
            await self.redis.client.setex(order_key, 86400, "1")
            
        return await self.modify_field(
            entity_id=player_id,
            field="diamond",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source
        )
        
    async def consume_diamond(
        self,
        player_id: str,
        amount: int,
        source: str
    ) -> Dict[str, Any]:
        """
        消耗钻石（并发安全）
        
        Args:
            player_id: 玩家ID
            amount: 数量
            source: 来源
            
        Returns:
            操作结果
        """
        # 先检查余额
        player = await self.get(player_id)
        if not player or int(player.get("diamond", 0)) < amount:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=player_id,
            field="diamond",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source
        )
        
    async def increment(
        self,
        entity_id: str,
        field: str,
        value: int,
        source: str = "unknown",
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """增加字段值"""
        return await self.modify_field(
            entity_id=entity_id,
            field=field,
            operation="incr",
            value=value,
            source=source
        )
        
    async def decrement_with_check(
        self,
        entity_id: str,
        field: str,
        value: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """减少字段值（带余额检查）"""
        # 先检查余额
        entity = await self.get(entity_id)
        if not entity or int(entity.get(field, 0)) < value:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=entity_id,
            field=field,
            operation="decr",
            value=value,
            source=source
        )
        
    async def batch_modify(
        self,
        entity_id: str,
        operations: list,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """批量修改字段"""
        results = []
        for op in operations:
            result = await self.modify_field(
                entity_id=entity_id,
                field=op["field"],
                operation=op["operation"],
                value=op["value"],
                source=source
            )
            results.append(result)
        return {"success": True, "results": results}