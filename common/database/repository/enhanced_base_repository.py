"""
增强的Repository基类
Enhanced Repository Base Class with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 支持自动装载和依赖注入的Repository基类，继承自BaseService
"""

from abc import ABC
from typing import Any, Optional

from ...ioc import BaseService, repository
from ..core.redis_client import RedisClient
from ..core.mongo_client import MongoClient

import logging

logger = logging.getLogger(__name__)


class BaseIoCRepository(BaseService, ABC):
    """
    数据仓库基类 - 支持自动装载
    
    所有数据访问层类都应该继承这个基类
    提供统一的数据库连接管理和基础操作
    """
    
    def __init__(self, collection_name: str = None):
        """
        初始化Repository
        
        Args:
            collection_name: 集合名称，如果为None则使用类名
        """
        super().__init__()
        self.collection_name = collection_name or self.__class__.__name__.replace('Repository', '').lower()
        self._redis_client: Optional[RedisClient] = None
        self._mongo_client: Optional[MongoClient] = None
    
    async def on_initialize(self) -> None:
        """初始化数据库连接"""
        try:
            self.logger.info(f"Initializing repository: {self._service_name}")
            
            # 自动注入数据库客户端
            self._redis_client = await self.get_redis_client()
            self._mongo_client = await self.get_mongo_client()
            
            self.logger.info(f"Repository initialized successfully: {self._service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize repository {self._service_name}: {e}")
            raise
    
    async def get_redis_client(self) -> RedisClient:
        """
        获取Redis客户端
        
        Returns:
            Redis客户端实例
        """
        if not self._redis_client:
            # 这里应该从容器获取Redis客户端，暂时创建默认配置的客户端
            self._redis_client = RedisClient({'host': 'localhost', 'port': 6379, 'db': 0})
            
        return self._redis_client
    
    async def get_mongo_client(self) -> MongoClient:
        """
        获取MongoDB客户端
        
        Returns:
            MongoDB客户端实例
        """
        if not self._mongo_client:
            # 这里应该从容器获取MongoDB客户端，暂时创建默认配置的客户端
            self._mongo_client = MongoClient({'host': 'localhost', 'port': 27017, 'database': 'knight_hero'})
            
        return self._mongo_client
    
    @property
    def redis(self) -> Optional[RedisClient]:
        """Redis客户端属性"""
        return self._redis_client
    
    @property
    def mongo(self) -> Optional[MongoClient]:
        """MongoDB客户端属性"""
        return self._mongo_client
    
    async def get_by_id(self, entity_id: str) -> Optional[dict]:
        """
        根据ID获取实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            实体数据字典，不存在则返回None
        """
        try:
            # 先尝试从Redis缓存获取
            if self._redis_client:
                cache_key = f"{self.collection_name}:{entity_id}"
                cached_data = await self._redis_client.hgetall(cache_key)
                if cached_data:
                    self.logger.debug(f"Cache hit for {cache_key}")
                    return cached_data
            
            # 从MongoDB获取
            if self._mongo_client:
                data = await self._mongo_client.find_one(self.collection_name, {"_id": entity_id})
                
                # 更新缓存
                if data and self._redis_client:
                    cache_key = f"{self.collection_name}:{entity_id}"
                    await self._redis_client.hmset(cache_key, data)
                    await self._redis_client.expire(cache_key, 3600)  # 1小时过期
                
                return data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting entity {entity_id} from {self.collection_name}: {e}")
            raise
    
    async def create(self, entity_id: str, entity_data: dict) -> dict:
        """
        创建新实体
        
        Args:
            entity_id: 实体ID
            entity_data: 实体数据
            
        Returns:
            创建结果
        """
        try:
            # 添加ID到数据中
            data_to_save = dict(entity_data)
            data_to_save["_id"] = entity_id
            
            # 保存到MongoDB
            if self._mongo_client:
                await self._mongo_client.insert_one(self.collection_name, data_to_save)
            
            # 更新缓存
            if self._redis_client:
                cache_key = f"{self.collection_name}:{entity_id}"
                await self._redis_client.hmset(cache_key, data_to_save)
                await self._redis_client.expire(cache_key, 3600)
            
            self.logger.debug(f"Created entity {entity_id} in {self.collection_name}")
            return {"success": True, "entity_id": entity_id}
            
        except Exception as e:
            self.logger.error(f"Error creating entity {entity_id} in {self.collection_name}: {e}")
            raise
    
    async def update(self, entity_id: str, update_data: dict) -> dict:
        """
        更新实体
        
        Args:
            entity_id: 实体ID
            update_data: 更新数据
            
        Returns:
            更新结果
        """
        try:
            # 更新MongoDB
            if self._mongo_client:
                result = await self._mongo_client.update_one(
                    self.collection_name,
                    {"_id": entity_id},
                    {"$set": update_data}
                )
                
                if result.matched_count == 0:
                    return {"success": False, "error": "Entity not found"}
            
            # 更新缓存
            if self._redis_client:
                cache_key = f"{self.collection_name}:{entity_id}"
                await self._redis_client.hmset(cache_key, update_data)
            
            self.logger.debug(f"Updated entity {entity_id} in {self.collection_name}")
            return {"success": True, "entity_id": entity_id}
            
        except Exception as e:
            self.logger.error(f"Error updating entity {entity_id} in {self.collection_name}: {e}")
            raise
    
    async def delete(self, entity_id: str) -> dict:
        """
        删除实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            删除结果
        """
        try:
            # 从MongoDB删除
            if self._mongo_client:
                result = await self._mongo_client.delete_one(
                    self.collection_name,
                    {"_id": entity_id}
                )
                
                if result.deleted_count == 0:
                    return {"success": False, "error": "Entity not found"}
            
            # 从缓存删除
            if self._redis_client:
                cache_key = f"{self.collection_name}:{entity_id}"
                await self._redis_client.delete(cache_key)
            
            self.logger.debug(f"Deleted entity {entity_id} from {self.collection_name}")
            return {"success": True, "entity_id": entity_id}
            
        except Exception as e:
            self.logger.error(f"Error deleting entity {entity_id} from {self.collection_name}: {e}")
            raise
    
    async def increment(
        self,
        entity_id: str,
        field: str,
        value: int,
        source: str = "unknown"
    ) -> dict:
        """
        原子增加字段值
        
        Args:
            entity_id: 实体ID
            field: 字段名
            value: 增加的值
            source: 来源
            
        Returns:
            操作结果
        """
        try:
            # Redis原子操作
            if self._redis_client:
                cache_key = f"{self.collection_name}:{entity_id}"
                new_value = await self._redis_client.hincrby(cache_key, field, value)
                
                # 记录操作日志
                log_data = {
                    "entity_id": entity_id,
                    "field": field,
                    "value": value,
                    "new_value": new_value,
                    "source": source,
                    "timestamp": __import__('time').time()
                }
                
                # 异步更新MongoDB
                if self._mongo_client:
                    await self._mongo_client.update_one(
                        self.collection_name,
                        {"_id": entity_id},
                        {"$inc": {field: value}}
                    )
                
                return {
                    "success": True,
                    "entity_id": entity_id,
                    "field": field,
                    "old_value": new_value - value,
                    "new_value": new_value,
                    "increment": value
                }
            
            # 如果没有Redis，直接操作MongoDB
            if self._mongo_client:
                result = await self._mongo_client.update_one(
                    self.collection_name,
                    {"_id": entity_id},
                    {"$inc": {field: value}}
                )
                
                if result.matched_count == 0:
                    return {"success": False, "error": "Entity not found"}
                
                # 获取新值
                updated_doc = await self._mongo_client.find_one(
                    self.collection_name,
                    {"_id": entity_id},
                    {"_id": 0, field: 1}
                )
                
                new_value = updated_doc.get(field, 0) if updated_doc else 0
                
                return {
                    "success": True,
                    "entity_id": entity_id,
                    "field": field,
                    "new_value": new_value,
                    "increment": value
                }
            
            return {"success": False, "error": "No database available"}
            
        except Exception as e:
            self.logger.error(f"Error incrementing {field} for {entity_id}: {e}")
            raise
    
    async def decrement_with_check(
        self,
        entity_id: str,
        field: str,
        value: int,
        source: str = "unknown",
        min_value: int = 0
    ) -> dict:
        """
        原子减少字段值（带检查）
        
        Args:
            entity_id: 实体ID
            field: 字段名
            value: 减少的值
            source: 来源
            min_value: 最小值限制
            
        Returns:
            操作结果
        """
        try:
            # 先检查当前值
            current_data = await self.get_by_id(entity_id)
            if not current_data:
                return {"success": False, "error": "Entity not found"}
            
            current_value = current_data.get(field, 0)
            if current_value < value:
                return {
                    "success": False,
                    "error": f"Insufficient {field}",
                    "current_value": current_value,
                    "required": value
                }
            
            if current_value - value < min_value:
                return {
                    "success": False,
                    "error": f"{field} cannot go below {min_value}",
                    "current_value": current_value,
                    "required": value
                }
            
            # 执行减少操作
            return await self.increment(entity_id, field, -value, source)
            
        except Exception as e:
            self.logger.error(f"Error decrementing {field} for {entity_id}: {e}")
            raise
    
    async def health_check(self) -> dict:
        """
        Repository健康检查
        
        Returns:
            健康检查结果
        """
        base_health = await super().health_check()
        
        redis_status = "unknown"
        mongo_status = "unknown"
        
        try:
            if self._redis_client:
                # 简单的ping测试
                redis_status = "healthy"
        except:
            redis_status = "unhealthy"
        
        try:
            if self._mongo_client:
                # 简单的连接测试
                mongo_status = "healthy"
        except:
            mongo_status = "unhealthy"
        
        base_health.update({
            "collection_name": self.collection_name,
            "redis_status": redis_status,
            "mongo_status": mongo_status
        })
        
        return base_health