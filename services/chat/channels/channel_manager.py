"""
频道管理器
Channel Manager

作者: lx
日期: 2025-06-18
描述: 负责聊天频道的创建、管理、玩家订阅和消息广播
"""
import asyncio
import time
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timedelta
import logging

from common.database import get_redis_cache, get_mongo_client
from common.utils import SnowflakeIdGenerator
from ..models import ChatMessage, ChannelInfo, ChatType, ChatStatistics


class ChannelSubscription:
    """频道订阅信息"""
    
    def __init__(self, player_id: str, channel_id: str):
        """
        初始化订阅信息
        
        Args:
            player_id: 玩家ID
            channel_id: 频道ID
        """
        self.player_id = player_id
        self.channel_id = channel_id
        self.subscribed_at = time.time()
        self.last_active = time.time()
        self.message_count = 0
    
    def update_activity(self) -> None:
        """更新活跃时间"""
        self.last_active = time.time()
        self.message_count += 1


class ChannelManager:
    """频道管理器"""
    
    def __init__(self):
        """初始化频道管理器"""
        self._redis_client = None
        self._mongo_client = None
        self._id_generator = SnowflakeIdGenerator()
        self._logger = logging.getLogger(__name__)
        
        # 内存中的频道信息
        self._channels: Dict[str, ChannelInfo] = {}
        self._subscriptions: Dict[str, Dict[str, ChannelSubscription]] = {}  # channel_id -> {player_id -> subscription}
        self._player_channels: Dict[str, Set[str]] = {}  # player_id -> {channel_ids}
        
        # Redis Pub/Sub
        self._pubsub = None
        self._subscriber_task = None
        
        # 统计信息
        self._statistics = ChatStatistics()
        
        # 配置常量
        self.MAX_CHANNEL_MEMBERS = 1000
        self.CHANNEL_CLEANUP_INTERVAL = 300  # 5分钟
        self.INACTIVE_TIMEOUT = 1800  # 30分钟无活动则视为非活跃
        
        # 默认频道
        self.DEFAULT_CHANNELS = [
            ("world", "世界聊天", ChatType.WORLD),
            ("system", "系统公告", ChatType.SYSTEM),
        ]
    
    async def initialize(self) -> bool:
        """
        初始化频道管理器
        
        Returns:
            初始化是否成功
        """
        try:
            # 获取数据库客户端
            self._redis_client = await get_redis_cache()
            self._mongo_client = await get_mongo_client()
            
            # 初始化Redis Pub/Sub
            await self._setup_pubsub()
            
            # 创建默认频道
            await self._create_default_channels()
            
            # 启动清理任务
            asyncio.create_task(self._cleanup_worker())
            
            # 启动统计更新任务
            asyncio.create_task(self._statistics_worker())
            
            self._logger.info("频道管理器初始化成功")
            return True
            
        except Exception as e:
            self._logger.error(f"频道管理器初始化失败: {e}")
            return False
    
    async def shutdown(self) -> None:
        """关闭频道管理器"""
        if self._subscriber_task and not self._subscriber_task.done():
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.close()
        
        self._logger.info("频道管理器已关闭")
    
    async def create_channel(self, 
                           channel_name: str, 
                           creator_id: str,
                           channel_type: ChatType = ChatType.CHANNEL,
                           description: Optional[str] = None,
                           max_members: int = None) -> Optional[ChannelInfo]:
        """
        创建聊天频道
        
        Args:
            channel_name: 频道名称
            creator_id: 创建者ID
            channel_type: 频道类型
            description: 频道描述
            max_members: 最大成员数
            
        Returns:
            频道信息，创建失败返回None
        """
        try:
            # 检查频道名称是否已存在
            if await self._channel_exists(channel_name):
                self._logger.warning(f"频道名称已存在: {channel_name}")
                return None
            
            # 生成频道ID
            channel_id = f"channel_{self._id_generator.generate()}"
            
            # 创建频道信息
            channel = ChannelInfo(
                channel_id=channel_id,
                channel_name=channel_name,
                channel_type=channel_type,
                description=description,
                creator_id=creator_id,
                created_at=datetime.now(),
                max_members=max_members or self.MAX_CHANNEL_MEMBERS
            )
            
            # 保存到内存和数据库
            self._channels[channel_id] = channel
            await self._save_channel_to_db(channel)
            
            # 初始化订阅信息
            self._subscriptions[channel_id] = {}
            
            # 创建者自动订阅
            await self.subscribe_channel(creator_id, channel_id)
            
            self._logger.info(f"创建频道成功: {channel_name} ({channel_id})")
            return channel
            
        except Exception as e:
            self._logger.error(f"创建频道失败: {e}, name: {channel_name}")
            return None
    
    async def delete_channel(self, channel_id: str, operator_id: str) -> bool:
        """
        删除聊天频道
        
        Args:
            channel_id: 频道ID
            operator_id: 操作者ID
            
        Returns:
            删除是否成功
        """
        try:
            channel = self._channels.get(channel_id)
            if not channel:
                return False
            
            # 检查权限（只有创建者可以删除）
            if channel.creator_id != operator_id:
                self._logger.warning(f"无权限删除频道: {operator_id} -> {channel_id}")
                return False
            
            # 移除所有订阅
            if channel_id in self._subscriptions:
                for player_id in list(self._subscriptions[channel_id].keys()):
                    await self.unsubscribe_channel(player_id, channel_id)
            
            # 从内存和数据库删除
            del self._channels[channel_id]
            await self._delete_channel_from_db(channel_id)
            
            self._logger.info(f"删除频道成功: {channel.channel_name} ({channel_id})")
            return True
            
        except Exception as e:
            self._logger.error(f"删除频道失败: {e}, channel_id: {channel_id}")
            return False
    
    async def subscribe_channel(self, player_id: str, channel_id: str) -> bool:
        """
        订阅频道
        
        Args:
            player_id: 玩家ID
            channel_id: 频道ID
            
        Returns:
            订阅是否成功
        """
        try:
            channel = self._channels.get(channel_id)
            if not channel:
                self._logger.warning(f"频道不存在: {channel_id}")
                return False
            
            # 检查是否已订阅
            if (channel_id in self._subscriptions and 
                player_id in self._subscriptions[channel_id]):
                return True
            
            # 检查频道成员数限制
            current_members = len(self._subscriptions.get(channel_id, {}))
            if current_members >= channel.max_members:
                self._logger.warning(f"频道成员已满: {channel_id}")
                return False
            
            # 创建订阅信息
            subscription = ChannelSubscription(player_id, channel_id)
            
            # 添加到内存
            if channel_id not in self._subscriptions:
                self._subscriptions[channel_id] = {}
            self._subscriptions[channel_id][player_id] = subscription
            
            if player_id not in self._player_channels:
                self._player_channels[player_id] = set()
            self._player_channels[player_id].add(channel_id)
            
            # 更新频道成员数
            channel.member_count = len(self._subscriptions[channel_id])
            
            # 保存到Redis
            await self._save_subscription_to_redis(player_id, channel_id)
            
            self._logger.debug(f"订阅频道成功: {player_id} -> {channel_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"订阅频道失败: {e}, player: {player_id}, channel: {channel_id}")
            return False
    
    async def unsubscribe_channel(self, player_id: str, channel_id: str) -> bool:
        """
        取消订阅频道
        
        Args:
            player_id: 玩家ID
            channel_id: 频道ID
            
        Returns:
            取消订阅是否成功
        """
        try:
            # 从内存删除
            if (channel_id in self._subscriptions and 
                player_id in self._subscriptions[channel_id]):
                del self._subscriptions[channel_id][player_id]
            
            if (player_id in self._player_channels and 
                channel_id in self._player_channels[player_id]):
                self._player_channels[player_id].remove(channel_id)
                
                # 如果玩家没有订阅任何频道，删除记录
                if not self._player_channels[player_id]:
                    del self._player_channels[player_id]
            
            # 更新频道成员数
            if channel_id in self._channels:
                self._channels[channel_id].member_count = len(
                    self._subscriptions.get(channel_id, {})
                )
            
            # 从Redis删除
            await self._remove_subscription_from_redis(player_id, channel_id)
            
            self._logger.debug(f"取消订阅频道成功: {player_id} -> {channel_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"取消订阅频道失败: {e}, player: {player_id}, channel: {channel_id}")
            return False
    
    async def broadcast_message(self, message: ChatMessage) -> int:
        """
        广播消息到频道
        
        Args:
            message: 聊天消息
            
        Returns:
            接收消息的玩家数量
        """
        try:
            channel_id = message.channel
            
            # 获取频道订阅者
            subscribers = self._subscriptions.get(channel_id, {})
            if not subscribers:
                return 0
            
            # 通过Redis Pub/Sub广播
            redis = self._redis_client.client
            message_data = message.to_json()
            
            # 发布到频道
            await redis.publish(f"chat:channel:{channel_id}", message_data)
            
            # 更新订阅者活跃时间
            for subscription in subscribers.values():
                subscription.update_activity()
            
            # 更新统计信息
            self._statistics.today_messages += 1
            self._statistics.total_messages += 1
            
            self._logger.debug(f"广播消息到频道: {channel_id}, 接收者: {len(subscribers)}")
            return len(subscribers)
            
        except Exception as e:
            self._logger.error(f"广播消息失败: {e}, channel: {message.channel}")
            return 0
    
    async def send_private_message(self, message: ChatMessage) -> bool:
        """
        发送私聊消息
        
        Args:
            message: 聊天消息
            
        Returns:
            发送是否成功
        """
        try:
            if not message.receiver_id:
                return False
            
            # 通过Redis Pub/Sub发送私聊
            redis = self._redis_client.client
            message_data = message.to_json()
            
            # 发布到玩家的私聊频道
            await redis.publish(f"chat:private:{message.receiver_id}", message_data)
            
            self._logger.debug(f"发送私聊消息: {message.sender_id} -> {message.receiver_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"发送私聊消息失败: {e}")
            return False
    
    async def get_channel_info(self, channel_id: str) -> Optional[ChannelInfo]:
        """
        获取频道信息
        
        Args:
            channel_id: 频道ID
            
        Returns:
            频道信息
        """
        return self._channels.get(channel_id)
    
    async def get_player_channels(self, player_id: str) -> List[ChannelInfo]:
        """
        获取玩家订阅的频道列表
        
        Args:
            player_id: 玩家ID
            
        Returns:
            频道信息列表
        """
        channel_ids = self._player_channels.get(player_id, set())
        channels = []
        
        for channel_id in channel_ids:
            channel = self._channels.get(channel_id)
            if channel:
                channels.append(channel)
        
        return channels
    
    async def get_channel_members(self, channel_id: str) -> List[str]:
        """
        获取频道成员列表
        
        Args:
            channel_id: 频道ID
            
        Returns:
            玩家ID列表
        """
        subscribers = self._subscriptions.get(channel_id, {})
        return list(subscribers.keys())
    
    async def get_all_channels(self) -> List[ChannelInfo]:
        """
        获取所有活跃频道
        
        Returns:
            频道信息列表
        """
        return [channel for channel in self._channels.values() if channel.is_active]
    
    async def get_statistics(self) -> ChatStatistics:
        """
        获取聊天统计信息
        
        Returns:
            统计信息
        """
        # 更新实时统计
        self._statistics.active_channels = len(
            [ch for ch in self._channels.values() if ch.is_active]
        )
        self._statistics.total_channels = len(self._channels)
        self._statistics.online_users = len(self._player_channels)
        self._statistics.updated_at = datetime.now()
        
        return self._statistics
    
    def is_player_subscribed(self, player_id: str, channel_id: str) -> bool:
        """
        检查玩家是否订阅了频道
        
        Args:
            player_id: 玩家ID
            channel_id: 频道ID
            
        Returns:
            是否已订阅
        """
        return (channel_id in self._subscriptions and 
                player_id in self._subscriptions[channel_id])
    
    # ========== 私有方法 ==========
    
    async def _setup_pubsub(self) -> None:
        """设置Redis Pub/Sub"""
        if not self._redis_client:
            return
        
        redis = self._redis_client.client
        self._pubsub = redis.pubsub()
        
        # 订阅所有聊天频道（用于监控和日志）
        await self._pubsub.psubscribe("chat:*")
        
        # 启动订阅监听任务
        self._subscriber_task = asyncio.create_task(self._pubsub_listener())
    
    async def _pubsub_listener(self) -> None:
        """Pub/Sub监听器"""
        if not self._pubsub:
            return
        
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "pmessage":
                    await self._handle_pubsub_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Pub/Sub监听器异常: {e}")
    
    async def _handle_pubsub_message(self, message: Dict[str, Any]) -> None:
        """处理Pub/Sub消息"""
        try:
            channel = message["channel"].decode('utf-8')
            data = message["data"]
            
            # 这里可以添加消息监控、日志记录等逻辑
            self._logger.debug(f"收到Pub/Sub消息: {channel}")
            
        except Exception as e:
            self._logger.warning(f"处理Pub/Sub消息失败: {e}")
    
    async def _create_default_channels(self) -> None:
        """创建默认频道"""
        for channel_name, description, chat_type in self.DEFAULT_CHANNELS:
            if not await self._channel_exists(channel_name):
                await self.create_channel(
                    channel_name=channel_name,
                    creator_id="system",
                    channel_type=chat_type,
                    description=description
                )
    
    async def _channel_exists(self, channel_name: str) -> bool:
        """检查频道名称是否存在"""
        for channel in self._channels.values():
            if channel.channel_name == channel_name:
                return True
        return False
    
    async def _save_channel_to_db(self, channel: ChannelInfo) -> None:
        """保存频道信息到数据库"""
        if not self._mongo_client:
            return
        
        try:
            collection = self._mongo_client["chat_channels"]
            await collection.insert_one(channel.to_dict())
        except Exception as e:
            self._logger.error(f"保存频道到数据库失败: {e}")
    
    async def _delete_channel_from_db(self, channel_id: str) -> None:
        """从数据库删除频道"""
        if not self._mongo_client:
            return
        
        try:
            collection = self._mongo_client["chat_channels"]
            await collection.delete_one({"channel_id": channel_id})
        except Exception as e:
            self._logger.error(f"从数据库删除频道失败: {e}")
    
    async def _save_subscription_to_redis(self, player_id: str, channel_id: str) -> None:
        """保存订阅信息到Redis"""
        if not self._redis_client:
            return
        
        try:
            redis = self._redis_client.client
            
            # 保存玩家的频道订阅列表
            await redis.sadd(f"player:{player_id}:channels", channel_id)
            
            # 保存频道的成员列表
            await redis.sadd(f"channel:{channel_id}:members", player_id)
            
        except Exception as e:
            self._logger.error(f"保存订阅信息到Redis失败: {e}")
    
    async def _remove_subscription_from_redis(self, player_id: str, channel_id: str) -> None:
        """从Redis删除订阅信息"""
        if not self._redis_client:
            return
        
        try:
            redis = self._redis_client.client
            
            # 删除玩家的频道订阅
            await redis.srem(f"player:{player_id}:channels", channel_id)
            
            # 删除频道的成员
            await redis.srem(f"channel:{channel_id}:members", player_id)
            
        except Exception as e:
            self._logger.error(f"从Redis删除订阅信息失败: {e}")
    
    async def _cleanup_worker(self) -> None:
        """清理工作协程"""
        while True:
            try:
                await asyncio.sleep(self.CHANNEL_CLEANUP_INTERVAL)
                await self._cleanup_inactive_subscriptions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"清理工作协程异常: {e}")
    
    async def _cleanup_inactive_subscriptions(self) -> None:
        """清理非活跃的订阅"""
        current_time = time.time()
        inactive_threshold = current_time - self.INACTIVE_TIMEOUT
        
        cleanup_count = 0
        
        for channel_id, subscriptions in list(self._subscriptions.items()):
            for player_id, subscription in list(subscriptions.items()):
                if subscription.last_active < inactive_threshold:
                    await self.unsubscribe_channel(player_id, channel_id)
                    cleanup_count += 1
        
        if cleanup_count > 0:
            self._logger.info(f"清理了 {cleanup_count} 个非活跃订阅")
    
    async def _statistics_worker(self) -> None:
        """统计信息更新工作协程"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟更新一次统计信息
                
                # 这里可以添加更复杂的统计逻辑
                # 比如计算活跃用户数、消息频率等
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"统计信息更新异常: {e}")


# 全局实例
_channel_manager: Optional[ChannelManager] = None


async def get_channel_manager() -> ChannelManager:
    """获取频道管理器实例"""
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
        await _channel_manager.initialize()
    return _channel_manager


async def close_channel_manager() -> None:
    """关闭频道管理器"""
    global _channel_manager
    if _channel_manager:
        await _channel_manager.shutdown()
        _channel_manager = None