"""
持久化服务
定时将Redis数据同步到MongoDB
作者: lx
日期: 2025-06-20
"""
import asyncio
from typing import Set
import time

class PersistenceService:
    """数据持久化服务"""
    
    def __init__(self, redis_client, mongo_client):
        """
        初始化持久化服务
        
        Args:
            redis_client: Redis客户端
            mongo_client: MongoDB客户端
        """
        self.redis = redis_client
        self.mongo = mongo_client
        self._running = False
        self._dirty_keys: Set[str] = set()
        
    async def start(self):
        """启动持久化服务"""
        self._running = True
        
        # 启动工作协程
        tasks = [
            asyncio.create_task(self._persistence_worker()),
            asyncio.create_task(self._scheduled_persistence())
        ]
        
        await asyncio.gather(*tasks)
        
    async def mark_dirty(self, collection: str, entity_id: str):
        """标记实体为脏数据"""
        key = f"{collection}:{entity_id}"
        self._dirty_keys.add(key)
        
    async def _persistence_worker(self):
        """持久化工作协程"""
        while self._running:
            if not self._dirty_keys:
                await asyncio.sleep(1)
                continue
                
            # 批量处理脏数据
            batch = []
            for _ in range(min(100, len(self._dirty_keys))):
                if self._dirty_keys:
                    batch.append(self._dirty_keys.pop())
                    
            if batch:
                await self._persist_batch(batch)
                
    async def _persist_batch(self, keys: list):
        """批量持久化"""
        for key in keys:
            try:
                # 解析collection和entity_id
                parts = key.split(":")
                if len(parts) != 2:
                    continue
                    
                collection, entity_id = parts
                
                # 从Redis获取数据
                data = await self.redis.client.hgetall(key)
                if not data:
                    continue
                    
                # 转换数据类型
                data["_id"] = entity_id
                
                # 更新到MongoDB
                await self.mongo[collection].replace_one(
                    {"_id": entity_id},
                    data,
                    upsert=True
                )
                
            except Exception as e:
                print(f"Persist error for {key}: {e}")
                # 重新加入脏数据集合
                self._dirty_keys.add(key)
                
    async def _scheduled_persistence(self):
        """定时全量持久化（每5分钟）"""
        while self._running:
            await asyncio.sleep(300)  # 5分钟
            
            try:
                # 扫描所有缓存键
                cursor = 0
                while True:
                    cursor, keys = await self.redis.client.scan(cursor, match="*:*", count=100)
                    
                    for key in keys:
                        self._dirty_keys.add(key)
                        
                    if cursor == 0:
                        break
                        
            except Exception as e:
                print(f"Scheduled persistence error: {e}")