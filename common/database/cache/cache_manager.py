"""
缓存管理器
统一管理缓存策略和操作
作者: lx
日期: 2025-06-20
"""
from typing import Optional, Any, Dict
import random

class CacheManager:
    """缓存管理器"""
    
    def __init__(self, redis_client):
        """
        初始化缓存管理器
        
        Args:
            redis_client: Redis客户端
        """
        self.redis = redis_client
        self._ttl_config = {
            "player": 300,      # 5分钟
            "item": 600,        # 10分钟
            "guild": 1800,      # 30分钟
            "config": 3600,     # 1小时
        }
        
    async def get(self, key: str, field: Optional[str] = None) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
            field: 字段名（用于哈希）
            
        Returns:
            缓存值
        """
        if field:
            return await self.redis.client.hget(key, field)
        else:
            return await self.redis.client.get(key)
            
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        entity_type: Optional[str] = None
    ):
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间
            entity_type: 实体类型
        """
        # 获取TTL
        if ttl is None and entity_type:
            base_ttl = self._ttl_config.get(entity_type, 300)
            # 添加±20%随机性防止缓存雪崩
            ttl = int(base_ttl * (0.8 + random.random() * 0.4))
            
        if isinstance(value, dict):
            await self.redis.client.hset(key, mapping=value)
        else:
            await self.redis.client.set(key, value)
            
        if ttl:
            await self.redis.client.expire(key, ttl)
            
    async def delete(self, key: str):
        """删除缓存"""
        await self.redis.client.delete(key)
        
    async def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        return await self.redis.client.exists(key) > 0