"""
公会数据仓库
处理公会相关的所有数据操作
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any, Optional
from ..repository.base_repository import BaseRepository
from ..concurrent.operation_type import OperationType
from ..models.guild_model import GuildModel

class GuildRepository(BaseRepository):
    """公会数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(redis_client, mongo_client, "guilds")
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """定义支持并发操作的字段"""
        meta = getattr(GuildModel, 'Meta', None)
        return getattr(meta, 'concurrent_fields', {}) if meta else {}
        
    async def add_exp(
        self,
        guild_id: str,
        exp: int,
        source: str = "activity"
    ) -> Dict[str, Any]:
        """
        增加公会经验（并发安全）
        
        Args:
            guild_id: 公会ID
            exp: 经验值
            source: 来源
            
        Returns:
            操作结果
        """
        return await self.modify_field(
            entity_id=guild_id,
            field="exp",
            operation=OperationType.INCREMENT.value,
            value=exp,
            source=source
        )
        
    async def add_funds(
        self,
        guild_id: str,
        amount: int,
        source: str = "donation"
    ) -> Dict[str, Any]:
        """
        增加公会资金（并发安全）
        
        Args:
            guild_id: 公会ID
            amount: 资金数量
            source: 来源
            
        Returns:
            操作结果
        """
        return await self.modify_field(
            entity_id=guild_id,
            field="funds",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source
        )
        
    async def consume_funds(
        self,
        guild_id: str,
        amount: int,
        source: str = "expenditure"
    ) -> Dict[str, Any]:
        """
        消耗公会资金（并发安全）
        
        Args:
            guild_id: 公会ID
            amount: 消耗数量
            source: 来源
            
        Returns:
            操作结果
        """
        # 先检查资金
        guild = await self.get(guild_id)
        if not guild or int(guild.get("funds", 0)) < amount:
            return {"success": False, "reason": "insufficient_funds"}
            
        return await self.modify_field(
            entity_id=guild_id,
            field="funds",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source
        )
        
    async def add_activity_points(
        self,
        guild_id: str,
        points: int,
        source: str = "member_activity"
    ) -> Dict[str, Any]:
        """
        增加活动积分（并发安全）
        
        Args:
            guild_id: 公会ID
            points: 积分数量
            source: 来源
            
        Returns:
            操作结果
        """
        return await self.modify_field(
            entity_id=guild_id,
            field="activity_points",
            operation=OperationType.INCREMENT.value,
            value=points,
            source=source
        )