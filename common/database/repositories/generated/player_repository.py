"""
Player数据仓库
自动生成，请勿手动修改
生成时间: 2025-06-20 12:16:01
"""
from typing import Dict, Any, Optional, List
from ...repository.base_repository import BaseRepository
from ...models.player_model import PlayerModel
from ...concurrent.operation_type import OperationType

class PlayerRepository(BaseRepository[PlayerModel]):
    """Player数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(
            redis_client=redis_client,
            mongo_client=mongo_client,
            collection_name="players"
        )
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """获取支持并发操作的字段"""
        return {'diamond': {'type': 'number', 'operations': ['incr', 'decr'], 'min': 0, 'max': 999999999}, 'gold': {'type': 'number', 'operations': ['incr', 'decr'], 'min': 0, 'max': 999999999}, 'exp': {'type': 'number', 'operations': ['incr'], 'min': 0, 'max': 999999999}, 'energy': {'type': 'number', 'operations': ['incr', 'decr'], 'min': 0, 'max': 999}}
        
    async def get_by_id(self, entity_id: str) -> Optional[PlayerModel]:
        """根据ID获取实体"""
        return await self.get(entity_id)
        
    async def create(self, data: Dict[str, Any]) -> PlayerModel:
        """创建新实体"""
        entity = PlayerModel(**data)
        await self.save(str(entity.id), entity)
        return entity
        
    async def update(self, entity_id: str, data: Dict[str, Any]) -> bool:
        """更新实体"""
        entity = await self.get(entity_id)
        if not entity:
            return False
            
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                
        return await self.save(entity_id, entity)
        
    # 自动生成的并发安全方法
    
    
    async def increment_diamond(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """增加diamond（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id,
            field="diamond",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    async def decrement_diamond(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """减少diamond（并发安全）"""
        # 先检查余额
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "diamond", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=entity_id,
            field="diamond",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    async def increment_gold(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """增加gold（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id,
            field="gold",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    async def decrement_gold(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """减少gold（并发安全）"""
        # 先检查余额
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "gold", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=entity_id,
            field="gold",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    async def increment_exp(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """增加exp（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id,
            field="exp",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    
    
    async def increment_energy(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """增加energy（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id,
            field="energy",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    
    
    async def decrement_energy(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """减少energy（并发安全）"""
        # 先检查余额
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "energy", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=entity_id,
            field="energy",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    
    