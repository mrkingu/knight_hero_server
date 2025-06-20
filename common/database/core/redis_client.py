"""
Redis客户端封装
提供连接池管理和基础操作
作者: lx
日期: 2025-06-20
"""
import redis.asyncio as redis
from typing import Optional

class RedisClient:
    """Redis异步客户端"""
    
    def __init__(self, config: dict):
        """
        初始化Redis客户端
        
        Args:
            config: Redis配置
                - host: 主机地址
                - port: 端口
                - db: 数据库号
                - password: 密码
                - pool_size: 连接池大小
        """
        self.config = config
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        
    async def connect(self):
        """建立连接"""
        self._pool = redis.ConnectionPool(
            host=self.config.get('host', 'localhost'),
            port=self.config.get('port', 6379),
            db=self.config.get('db', 0),
            password=self.config.get('password'),
            max_connections=self.config.get('pool_size', 100),
            decode_responses=True
        )
        self._client = redis.Redis(connection_pool=self._pool)
        
    async def disconnect(self):
        """断开连接"""
        if self._client:
            await self._client.close()
            
    @property
    def client(self) -> redis.Redis:
        """获取Redis客户端实例"""
        if not self._client:
            raise RuntimeError("Redis client not connected")
        return self._client