"""
Item数据仓库
自动生成，请勿手动修改
生成时间: 2025-06-20 12:16:01
"""
from typing import Dict, Any, Optional, List
from ...repository.base_repository import BaseRepository
from ...models.item_model import ItemModel
from ...concurrent.operation_type import OperationType

class ItemRepository(BaseRepository[ItemModel]):
    """Item数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(
            redis_client=redis_client,
            mongo_client=mongo_client,
            collection_name="items"
        )
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """获取支持并发操作的字段"""
        return {}
        
    async def get_by_id(self, entity_id: str) -> Optional[ItemModel]:
        """根据ID获取实体"""
        return await self.get(entity_id)
        
    async def create(self, data: Dict[str, Any]) -> ItemModel:
        """创建新实体"""
        entity = ItemModel(**data)
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
    