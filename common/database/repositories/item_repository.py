"""
道具数据仓库
处理道具相关的所有数据操作
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from ..repository.base_repository import BaseRepository
from ..concurrent.operation_type import OperationType
from ..models.item_model import ItemModel

class ItemRepository(BaseRepository):
    """道具数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(redis_client, mongo_client, "items")
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """定义支持并发操作的字段"""
        meta = getattr(ItemModel, 'Meta', None)
        return getattr(meta, 'concurrent_fields', {}) if meta else {}
        
    async def add_item_quantity(
        self,
        item_id: str,
        quantity: int,
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        增加道具数量（并发安全）
        
        Args:
            item_id: 道具ID
            quantity: 增加数量
            source: 来源
            
        Returns:
            操作结果
        """
        return await self.modify_field(
            entity_id=item_id,
            field="quantity",
            operation=OperationType.INCREMENT.value,
            value=quantity,
            source=source
        )
        
    async def consume_item(
        self,
        item_id: str,
        quantity: int,
        source: str = "unknown"
    ) -> Dict[str, Any]:
        """
        消耗道具（并发安全）
        
        Args:
            item_id: 道具ID
            quantity: 消耗数量
            source: 来源
            
        Returns:
            操作结果
        """
        # 先检查数量
        item = await self.get(item_id)
        if not item or int(item.get("quantity", 0)) < quantity:
            return {"success": False, "reason": "insufficient_quantity"}
            
        return await self.modify_field(
            entity_id=item_id,
            field="quantity",
            operation=OperationType.DECREMENT.value,
            value=quantity,
            source=source
        )
        
    async def reduce_durability(
        self,
        item_id: str,
        durability_loss: int,
        source: str = "usage"
    ) -> Dict[str, Any]:
        """
        减少道具耐久度
        
        Args:
            item_id: 道具ID
            durability_loss: 耐久度损失
            source: 来源
            
        Returns:
            操作结果
        """
        return await self.modify_field(
            entity_id=item_id,
            field="durability",
            operation=OperationType.DECREMENT.value,
            value=durability_loss,
            source=source
        )