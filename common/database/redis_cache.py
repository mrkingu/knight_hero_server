"""
Redis缓存层
高性能缓存实现
作者: lx
日期: 2025-06-20
"""
from .core.redis_client import RedisClient
from .cache.cache_manager import CacheManager

class RedisCache:
    """Redis缓存封装类"""
    
    def __init__(self, config: dict):
        """初始化Redis缓存"""
        self.client = RedisClient(config)
        self.manager = CacheManager(self.client)
        
    async def connect(self):
        """连接Redis"""
        await self.client.connect()
        
    async def disconnect(self):
        """断开连接"""
        await self.client.disconnect()