"""
MongoDB客户端封装
使用Motor异步驱动
作者: lx
日期: 2025-06-20
"""
import motor.motor_asyncio as motor
from typing import Optional, Any, Dict

class MongoClient:
    """MongoDB异步客户端"""
    
    def __init__(self, config: dict):
        """
        初始化MongoDB客户端
        
        Args:
            config: MongoDB配置
                - uri: 连接字符串
                - database: 数据库名
                - max_pool_size: 最大连接池大小
                - min_pool_size: 最小连接池大小
        """
        self.config = config
        self._client: Optional[motor.AsyncIOMotorClient] = None
        self._database: Optional[motor.AsyncIOMotorDatabase] = None
        
    async def connect(self):
        """建立连接"""
        self._client = motor.AsyncIOMotorClient(
            self.config.get('uri', 'mongodb://localhost:27017'),
            maxPoolSize=self.config.get('max_pool_size', 100),
            minPoolSize=self.config.get('min_pool_size', 10)
        )
        self._database = self._client[self.config.get('database', 'game_db')]
        
    async def disconnect(self):
        """断开连接"""
        if self._client:
            self._client.close()
            
    @property
    def database(self) -> motor.AsyncIOMotorDatabase:
        """获取数据库实例"""
        if not self._database:
            raise RuntimeError("MongoDB client not connected")
        return self._database
        
    def __getitem__(self, collection_name: str) -> motor.AsyncIOMotorCollection:
        """获取集合"""
        return self.database[collection_name]