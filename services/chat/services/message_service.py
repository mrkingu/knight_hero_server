"""
消息存储服务
Message Storage Service

作者: lx
日期: 2025-06-18
描述: 负责聊天消息的存储、检索和管理，支持Redis缓存和MongoDB持久化
"""
import asyncio
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from common.database import get_redis_cache, get_mongo_client
from common.utils import SnowflakeIdGenerator
from ..models import ChatMessage, OfflineMessage, ChatType, MessageStatus


class MessageStorage:
    """消息存储管理器"""
    
    def __init__(self):
        """初始化消息存储管理器"""
        self._redis_client = None
        self._mongo_client = None
        self._id_generator = SnowflakeIdGenerator()
        self._persistence_queue = asyncio.Queue(maxsize=10000)
        self._persistence_task = None
        self._logger = logging.getLogger(__name__)
        
        # 配置常量
        self.REDIS_MESSAGE_LIMIT = 100  # Redis中每个频道保存的最大消息数
        self.REDIS_EXPIRE_TIME = 7 * 24 * 3600  # Redis消息过期时间（7天）
        self.MONGO_COLLECTION = "chat_messages"  # MongoDB集合名
        self.OFFLINE_COLLECTION = "offline_messages"  # 离线消息集合名
        
    async def initialize(self) -> bool:
        """
        初始化存储服务
        
        Returns:
            初始化是否成功
        """
        try:
            # 获取数据库客户端
            self._redis_client = await get_redis_cache()
            self._mongo_client = await get_mongo_client()
            
            # 启动持久化任务
            self._persistence_task = asyncio.create_task(self._persistence_worker())
            
            self._logger.info("消息存储服务初始化成功")
            return True
            
        except Exception as e:
            self._logger.error(f"消息存储服务初始化失败: {e}")
            return False
    
    async def shutdown(self) -> None:
        """关闭存储服务"""
        if self._persistence_task and not self._persistence_task.done():
            self._persistence_task.cancel()
            try:
                await self._persistence_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("消息存储服务已关闭")
    
    async def save_message(self, msg: ChatMessage) -> bool:
        """
        保存聊天消息
        
        Args:
            msg: 聊天消息对象
            
        Returns:
            保存是否成功
        """
        try:
            # 1. 设置消息ID和时间戳
            if not msg.message_id:
                msg.message_id = str(self._id_generator.generate())
            if not msg.created_at:
                msg.created_at = datetime.now()
            
            # 2. 保存到Redis（最近消息缓存）
            await self._save_to_redis(msg)
            
            # 3. 异步持久化到MongoDB
            await self._queue_for_persistence(msg)
            
            # 4. 如果是私聊，处理离线消息
            if msg.chat_type == ChatType.PRIVATE and msg.receiver_id:
                await self._handle_offline_message(msg)
            
            msg.status = MessageStatus.SENT
            return True
            
        except Exception as e:
            self._logger.error(f"保存消息失败: {e}, message_id: {msg.message_id}")
            return False
    
    async def get_history(self, 
                         channel: str, 
                         count: int = 50, 
                         before_timestamp: Optional[float] = None) -> List[ChatMessage]:
        """
        获取历史消息
        
        Args:
            channel: 频道名称
            count: 消息数量
            before_timestamp: 时间戳之前的消息
            
        Returns:
            历史消息列表
        """
        try:
            messages = []
            
            # 1. 先从Redis获取
            redis_messages = await self._get_from_redis(channel, count, before_timestamp)
            messages.extend(redis_messages)
            
            # 2. 如果Redis中消息不足，从MongoDB补充
            if len(messages) < count:
                remaining_count = count - len(messages)
                oldest_timestamp = None
                
                if messages:
                    oldest_timestamp = min(msg.timestamp for msg in messages)
                elif before_timestamp:
                    oldest_timestamp = before_timestamp
                
                mongo_messages = await self._get_from_mongo(
                    channel, 
                    remaining_count, 
                    oldest_timestamp
                )
                messages.extend(mongo_messages)
            
            # 3. 按时间戳排序（最新的在前）
            messages.sort(key=lambda x: x.timestamp, reverse=True)
            
            return messages[:count]
            
        except Exception as e:
            self._logger.error(f"获取历史消息失败: {e}, channel: {channel}")
            return []
    
    async def get_offline_messages(self, player_id: str) -> List[OfflineMessage]:
        """
        获取玩家的离线消息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            离线消息列表
        """
        try:
            if not self._mongo_client:
                return []
            
            # 查询未读的离线消息
            collection = self._mongo_client[self.OFFLINE_COLLECTION]
            cursor = collection.find({
                "player_id": player_id,
                "is_read": False,
                "expire_at": {"$gt": datetime.now()}
            }).sort("created_at", 1)
            
            offline_messages = []
            async for doc in cursor:
                # 转换消息数据
                message_data = doc.get("message", {})
                if message_data:
                    chat_message = ChatMessage(**message_data)
                    offline_msg = OfflineMessage(
                        offline_id=str(doc["_id"]),
                        player_id=doc["player_id"],
                        message=chat_message,
                        created_at=doc["created_at"],
                        expire_at=doc.get("expire_at"),
                        is_read=doc["is_read"]
                    )
                    offline_messages.append(offline_msg)
            
            return offline_messages
            
        except Exception as e:
            self._logger.error(f"获取离线消息失败: {e}, player_id: {player_id}")
            return []
    
    async def mark_offline_messages_read(self, player_id: str, message_ids: List[str]) -> bool:
        """
        标记离线消息为已读
        
        Args:
            player_id: 玩家ID
            message_ids: 消息ID列表
            
        Returns:
            操作是否成功
        """
        try:
            if not self._mongo_client or not message_ids:
                return False
            
            from bson import ObjectId
            
            # 转换消息ID
            object_ids = []
            for msg_id in message_ids:
                try:
                    object_ids.append(ObjectId(msg_id))
                except:
                    continue
            
            if not object_ids:
                return False
            
            # 批量更新
            collection = self._mongo_client[self.OFFLINE_COLLECTION]
            result = await collection.update_many(
                {
                    "_id": {"$in": object_ids},
                    "player_id": player_id
                },
                {
                    "$set": {"is_read": True}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            self._logger.error(f"标记离线消息已读失败: {e}, player_id: {player_id}")
            return False
    
    async def delete_message(self, message_id: str, channel: str) -> bool:
        """
        删除消息
        
        Args:
            message_id: 消息ID
            channel: 频道名称
            
        Returns:
            删除是否成功
        """
        try:
            # 1. 从Redis删除
            await self._delete_from_redis(message_id, channel)
            
            # 2. 从MongoDB删除（软删除）
            if self._mongo_client:
                collection = self._mongo_client[self.MONGO_COLLECTION]
                await collection.update_one(
                    {"message_id": message_id},
                    {"$set": {"status": MessageStatus.DELETED.value}}
                )
            
            return True
            
        except Exception as e:
            self._logger.error(f"删除消息失败: {e}, message_id: {message_id}")
            return False
    
    async def clean_expired_messages(self) -> int:
        """
        清理过期消息
        
        Returns:
            清理的消息数量
        """
        try:
            if not self._mongo_client:
                return 0
            
            # 清理过期的离线消息
            collection = self._mongo_client[self.OFFLINE_COLLECTION]
            result = await collection.delete_many({
                "expire_at": {"$lt": datetime.now()}
            })
            
            cleaned_count = result.deleted_count
            if cleaned_count > 0:
                self._logger.info(f"清理了 {cleaned_count} 条过期离线消息")
            
            return cleaned_count
            
        except Exception as e:
            self._logger.error(f"清理过期消息失败: {e}")
            return 0
    
    # ========== 私有方法 ==========
    
    async def _save_to_redis(self, msg: ChatMessage) -> None:
        """保存消息到Redis"""
        if not self._redis_client:
            return
        
        redis = self._redis_client.client
        key = f"chat:{msg.channel}:messages"
        
        # 添加到列表头部
        await redis.lpush(key, msg.to_json())
        
        # 限制列表长度
        await redis.ltrim(key, 0, self.REDIS_MESSAGE_LIMIT - 1)
        
        # 设置过期时间
        await redis.expire(key, self.REDIS_EXPIRE_TIME)
    
    async def _get_from_redis(self, 
                             channel: str, 
                             count: int,
                             before_timestamp: Optional[float] = None) -> List[ChatMessage]:
        """从Redis获取消息"""
        if not self._redis_client:
            return []
        
        redis = self._redis_client.client
        key = f"chat:{channel}:messages"
        
        # 获取消息列表
        raw_messages = await redis.lrange(key, 0, count - 1)
        
        messages = []
        for raw_msg in raw_messages:
            try:
                msg = ChatMessage.from_json(raw_msg)
                
                # 过滤时间戳
                if before_timestamp and msg.timestamp >= before_timestamp:
                    continue
                
                messages.append(msg)
                
                if len(messages) >= count:
                    break
                    
            except Exception as e:
                self._logger.warning(f"解析Redis消息失败: {e}")
                continue
        
        return messages
    
    async def _get_from_mongo(self, 
                             channel: str, 
                             count: int,
                             before_timestamp: Optional[float] = None) -> List[ChatMessage]:
        """从MongoDB获取消息"""
        if not self._mongo_client:
            return []
        
        try:
            collection = self._mongo_client[self.MONGO_COLLECTION]
            
            # 构建查询条件
            query = {
                "channel": channel,
                "status": {"$ne": MessageStatus.DELETED.value}
            }
            
            if before_timestamp:
                query["timestamp"] = {"$lt": before_timestamp}
            
            # 按时间戳降序查询
            cursor = collection.find(query).sort("timestamp", -1).limit(count)
            
            messages = []
            async for doc in cursor:
                try:
                    # 移除MongoDB的_id字段
                    doc.pop("_id", None)
                    msg = ChatMessage(**doc)
                    messages.append(msg)
                except Exception as e:
                    self._logger.warning(f"解析MongoDB消息失败: {e}")
                    continue
            
            return messages
            
        except Exception as e:
            self._logger.error(f"从MongoDB获取消息失败: {e}")
            return []
    
    async def _delete_from_redis(self, message_id: str, channel: str) -> None:
        """从Redis删除消息"""
        if not self._redis_client:
            return
        
        try:
            redis = self._redis_client.client
            key = f"chat:{channel}:messages"
            
            # 获取所有消息，找到对应的消息并删除
            messages = await redis.lrange(key, 0, -1)
            for i, raw_msg in enumerate(messages):
                try:
                    msg = ChatMessage.from_json(raw_msg)
                    if msg.message_id == message_id:
                        # 删除指定索引的元素
                        await redis.lrem(key, 1, raw_msg)
                        break
                except:
                    continue
                    
        except Exception as e:
            self._logger.warning(f"从Redis删除消息失败: {e}")
    
    async def _queue_for_persistence(self, msg: ChatMessage) -> None:
        """将消息加入持久化队列"""
        try:
            await self._persistence_queue.put(msg.to_dict())
        except asyncio.QueueFull:
            self._logger.warning(f"持久化队列已满，丢弃消息: {msg.message_id}")
    
    async def _persistence_worker(self) -> None:
        """持久化工作协程"""
        batch = []
        batch_size = 100
        batch_timeout = 5.0  # 5秒
        
        while True:
            try:
                # 收集批量消息
                deadline = time.time() + batch_timeout
                
                while len(batch) < batch_size and time.time() < deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    
                    try:
                        msg_data = await asyncio.wait_for(
                            self._persistence_queue.get(),
                            timeout=remaining
                        )
                        batch.append(msg_data)
                    except asyncio.TimeoutError:
                        break
                
                # 批量保存到MongoDB
                if batch:
                    await self._batch_save_to_mongo(batch)
                    batch = []
                    
            except asyncio.CancelledError:
                # 保存剩余的消息
                if batch:
                    await self._batch_save_to_mongo(batch)
                break
            except Exception as e:
                self._logger.error(f"持久化工作协程异常: {e}")
                await asyncio.sleep(1)
    
    async def _batch_save_to_mongo(self, message_batch: List[Dict[str, Any]]) -> None:
        """批量保存消息到MongoDB"""
        if not self._mongo_client or not message_batch:
            return
        
        try:
            collection = self._mongo_client[self.MONGO_COLLECTION]
            await collection.insert_many(message_batch, ordered=False)
            
            self._logger.debug(f"批量保存 {len(message_batch)} 条消息到MongoDB")
            
        except Exception as e:
            self._logger.error(f"批量保存到MongoDB失败: {e}")
    
    async def _handle_offline_message(self, msg: ChatMessage) -> None:
        """处理离线消息"""
        if not msg.receiver_id or not self._mongo_client:
            return
        
        try:
            # 检查接收者是否在线（这里需要与用户服务集成）
            # 暂时假设离线，直接保存离线消息
            
            offline_msg = OfflineMessage(
                offline_id=str(self._id_generator.generate()),
                player_id=msg.receiver_id,
                message=msg,
                created_at=datetime.now(),
                expire_at=datetime.now() + timedelta(days=7)  # 7天后过期
            )
            
            collection = self._mongo_client[self.OFFLINE_COLLECTION]
            await collection.insert_one(offline_msg.to_dict())
            
            self._logger.debug(f"保存离线消息: {msg.message_id} -> {msg.receiver_id}")
            
        except Exception as e:
            self._logger.error(f"处理离线消息失败: {e}")


# 全局实例
_message_storage: Optional[MessageStorage] = None


async def get_message_storage() -> MessageStorage:
    """获取消息存储服务实例"""
    global _message_storage
    if _message_storage is None:
        _message_storage = MessageStorage()
        await _message_storage.initialize()
    return _message_storage


async def close_message_storage() -> None:
    """关闭消息存储服务"""
    global _message_storage
    if _message_storage:
        await _message_storage.shutdown()
        _message_storage = None