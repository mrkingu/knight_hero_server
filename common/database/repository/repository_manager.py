"""
仓库管理器
统一管理所有Repository实例
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any
from .player_repository import PlayerRepository

class RepositoryManager:
    """仓库管理器"""
    
    def __init__(self, redis_client, mongo_client):
        """初始化仓库管理器"""
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self._repositories = {}
        
    async def initialize(self, operation_logger):
        """初始化仓库"""
        self.operation_logger = operation_logger
        
    def get_repository(self, entity_type: str):
        """获取指定类型的仓库"""
        if entity_type not in self._repositories:
            if entity_type == "players":
                self._repositories[entity_type] = PlayerRepository(
                    self.redis_client, 
                    self.mongo_client
                )
            else:
                raise ValueError(f"Unknown repository type: {entity_type}")
                
        return self._repositories[entity_type]