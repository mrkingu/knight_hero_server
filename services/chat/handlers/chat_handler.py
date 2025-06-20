"""
聊天消息处理器
Chat Message Handler

作者: lx
日期: 2025-06-18
描述: 处理聊天消息的发送、历史消息拉取、频道管理等功能
"""
import asyncio
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from common.utils import SnowflakeIdGenerator
from ..models import ChatMessage, ChatType, MessageStatus, ChannelInfo
from ..services.message_service import get_message_storage
from ..channels.channel_manager import get_channel_manager
from ..filters.word_filter import get_word_filter


class ChatHandler:
    """聊天消息处理器"""
    
    def __init__(self):
        """初始化聊天处理器"""
        self._message_storage = None
        self._channel_manager = None
        self._word_filter = None
        self._id_generator = SnowflakeIdGenerator()
        self._logger = logging.getLogger(__name__)
        
        # 消息速率限制（防刷屏）
        self._rate_limits: Dict[str, List[float]] = {}  # player_id -> [timestamps]
        self.MAX_MESSAGES_PER_MINUTE = 20
        self.RATE_LIMIT_WINDOW = 60  # 秒
        
        # 消息长度限制
        self.MAX_MESSAGE_LENGTH = 500
        self.MIN_MESSAGE_LENGTH = 1
    
    async def initialize(self) -> bool:
        """
        初始化聊天处理器
        
        Returns:
            初始化是否成功
        """
        try:
            # 获取服务实例
            self._message_storage = await get_message_storage()
            self._channel_manager = await get_channel_manager()
            self._word_filter = get_word_filter()
            
            self._logger.info("聊天处理器初始化成功")
            return True
            
        except Exception as e:
            self._logger.error(f"聊天处理器初始化失败: {e}")
            return False
    
    async def send_message(self, 
                          sender_id: str,
                          sender_name: str,
                          chat_type: ChatType,
                          content: str,
                          channel: Optional[str] = None,
                          receiver_id: Optional[str] = None,
                          receiver_name: Optional[str] = None,
                          extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        发送聊天消息
        
        Args:
            sender_id: 发送者ID
            sender_name: 发送者昵称
            chat_type: 聊天类型
            content: 消息内容
            channel: 频道名称
            receiver_id: 接收者ID（私聊时必填）
            receiver_name: 接收者昵称
            extra_data: 扩展数据
            
        Returns:
            处理结果
        """
        try:
            # 1. 基础验证
            validation_result = await self._validate_message(
                sender_id, chat_type, content, channel, receiver_id
            )
            if not validation_result["success"]:
                return validation_result
            
            # 2. 速率限制检查
            if not await self._check_rate_limit(sender_id):
                return {
                    "success": False,
                    "error": "发送消息过于频繁，请稍后再试",
                    "error_code": "RATE_LIMIT_EXCEEDED"
                }
            
            # 3. 敏感词过滤
            filtered_content, detected_words = self._word_filter.filter_text(content)
            
            # 4. 构造消息对象
            message = ChatMessage(
                message_id=str(self._id_generator.generate()),
                chat_type=chat_type,
                channel=channel or self._get_default_channel(chat_type),
                sender_id=sender_id,
                sender_name=sender_name,
                receiver_id=receiver_id,
                receiver_name=receiver_name,
                content=filtered_content,
                original_content=content if detected_words else None,
                timestamp=time.time(),
                created_at=datetime.now(),
                status=MessageStatus.PENDING,
                extra_data=extra_data
            )
            
            # 5. 保存消息
            save_success = await self._message_storage.save_message(message)
            if not save_success:
                return {
                    "success": False,
                    "error": "消息保存失败",
                    "error_code": "SAVE_FAILED"
                }
            
            # 6. 广播消息
            broadcast_count = 0
            if chat_type == ChatType.PRIVATE:
                # 私聊消息
                broadcast_success = await self._channel_manager.send_private_message(message)
                broadcast_count = 1 if broadcast_success else 0
            else:
                # 频道广播
                broadcast_count = await self._channel_manager.broadcast_message(message)
            
            # 7. 更新速率限制
            self._update_rate_limit(sender_id)
            
            # 8. 构造响应
            result = {
                "success": True,
                "message_id": message.message_id,
                "timestamp": message.timestamp,
                "broadcast_count": broadcast_count,
                "filtered": len(detected_words) > 0
            }
            
            if detected_words:
                result["detected_words"] = detected_words
                result["filtered_content"] = filtered_content
            
            self._logger.debug(f"发送消息成功: {sender_id} -> {message.message_id}")
            return result
            
        except Exception as e:
            self._logger.error(f"发送消息失败: {e}, sender: {sender_id}")
            return {
                "success": False,
                "error": "服务器内部错误",
                "error_code": "INTERNAL_ERROR"
            }
    
    async def get_history_messages(self, 
                                  player_id: str,
                                  channel: str,
                                  count: int = 50,
                                  before_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        获取历史消息
        
        Args:
            player_id: 请求玩家ID
            channel: 频道名称
            count: 消息数量（最大100）
            before_timestamp: 时间戳之前的消息
            
        Returns:
            历史消息列表
        """
        try:
            # 1. 参数验证
            if count <= 0 or count > 100:
                count = 50
            
            # 2. 权限检查
            if not await self._check_channel_access(player_id, channel):
                return {
                    "success": False,
                    "error": "无权限访问该频道",
                    "error_code": "ACCESS_DENIED"
                }
            
            # 3. 获取历史消息
            messages = await self._message_storage.get_history(
                channel, count, before_timestamp
            )
            
            # 4. 转换为字典格式
            message_list = []
            for msg in messages:
                msg_dict = msg.to_dict()
                # 移除敏感信息
                msg_dict.pop("original_content", None)
                message_list.append(msg_dict)
            
            return {
                "success": True,
                "messages": message_list,
                "count": len(message_list),
                "channel": channel
            }
            
        except Exception as e:
            self._logger.error(f"获取历史消息失败: {e}, player: {player_id}, channel: {channel}")
            return {
                "success": False,
                "error": "获取历史消息失败",
                "error_code": "FETCH_FAILED"
            }
    
    async def get_offline_messages(self, player_id: str) -> Dict[str, Any]:
        """
        获取离线消息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            离线消息列表
        """
        try:
            # 获取离线消息
            offline_messages = await self._message_storage.get_offline_messages(player_id)
            
            # 转换为字典格式
            message_list = []
            message_ids = []
            
            for offline_msg in offline_messages:
                msg_dict = offline_msg.to_dict()
                message_list.append(msg_dict)
                message_ids.append(offline_msg.offline_id)
            
            # 标记为已读
            if message_ids:
                await self._message_storage.mark_offline_messages_read(player_id, message_ids)
            
            return {
                "success": True,
                "messages": message_list,
                "count": len(message_list)
            }
            
        except Exception as e:
            self._logger.error(f"获取离线消息失败: {e}, player: {player_id}")
            return {
                "success": False,
                "error": "获取离线消息失败",
                "error_code": "FETCH_FAILED"
            }
    
    async def join_channel(self, player_id: str, channel_name: str) -> Dict[str, Any]:
        """
        加入聊天频道
        
        Args:
            player_id: 玩家ID
            channel_name: 频道名称
            
        Returns:
            加入结果
        """
        try:
            # 查找频道
            channel_id = await self._find_channel_by_name(channel_name)
            if not channel_id:
                return {
                    "success": False,
                    "error": "频道不存在",
                    "error_code": "CHANNEL_NOT_FOUND"
                }
            
            # 订阅频道
            success = await self._channel_manager.subscribe_channel(player_id, channel_id)
            
            if success:
                return {
                    "success": True,
                    "channel_id": channel_id,
                    "channel_name": channel_name
                }
            else:
                return {
                    "success": False,
                    "error": "加入频道失败",
                    "error_code": "JOIN_FAILED"
                }
                
        except Exception as e:
            self._logger.error(f"加入频道失败: {e}, player: {player_id}, channel: {channel_name}")
            return {
                "success": False,
                "error": "服务器内部错误",
                "error_code": "INTERNAL_ERROR"
            }
    
    async def leave_channel(self, player_id: str, channel_name: str) -> Dict[str, Any]:
        """
        离开聊天频道
        
        Args:
            player_id: 玩家ID
            channel_name: 频道名称
            
        Returns:
            离开结果
        """
        try:
            # 查找频道
            channel_id = await self._find_channel_by_name(channel_name)
            if not channel_id:
                return {
                    "success": False,
                    "error": "频道不存在",
                    "error_code": "CHANNEL_NOT_FOUND"
                }
            
            # 取消订阅频道
            success = await self._channel_manager.unsubscribe_channel(player_id, channel_id)
            
            return {
                "success": success,
                "channel_id": channel_id,
                "channel_name": channel_name
            }
            
        except Exception as e:
            self._logger.error(f"离开频道失败: {e}, player: {player_id}, channel: {channel_name}")
            return {
                "success": False,
                "error": "服务器内部错误",
                "error_code": "INTERNAL_ERROR"
            }
    
    async def create_channel(self, 
                           creator_id: str,
                           channel_name: str,
                           description: Optional[str] = None,
                           max_members: Optional[int] = None) -> Dict[str, Any]:
        """
        创建聊天频道
        
        Args:
            creator_id: 创建者ID
            channel_name: 频道名称
            description: 频道描述
            max_members: 最大成员数
            
        Returns:
            创建结果
        """
        try:
            # 验证频道名称
            if not channel_name or len(channel_name.strip()) < 2:
                return {
                    "success": False,
                    "error": "频道名称太短",
                    "error_code": "INVALID_NAME"
                }
            
            if len(channel_name) > 50:
                return {
                    "success": False,
                    "error": "频道名称太长",
                    "error_code": "NAME_TOO_LONG"
                }
            
            # 创建频道
            channel = await self._channel_manager.create_channel(
                channel_name=channel_name.strip(),
                creator_id=creator_id,
                channel_type=ChatType.CHANNEL,
                description=description,
                max_members=max_members
            )
            
            if channel:
                return {
                    "success": True,
                    "channel_id": channel.channel_id,
                    "channel_name": channel.channel_name,
                    "created_at": channel.created_at.isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "创建频道失败",
                    "error_code": "CREATE_FAILED"
                }
                
        except Exception as e:
            self._logger.error(f"创建频道失败: {e}, creator: {creator_id}, name: {channel_name}")
            return {
                "success": False,
                "error": "服务器内部错误",
                "error_code": "INTERNAL_ERROR"
            }
    
    async def get_channel_list(self, player_id: str) -> Dict[str, Any]:
        """
        获取频道列表
        
        Args:
            player_id: 玩家ID
            
        Returns:
            频道列表
        """
        try:
            # 获取所有活跃频道
            all_channels = await self._channel_manager.get_all_channels()
            
            # 获取玩家订阅的频道
            player_channels = await self._channel_manager.get_player_channels(player_id)
            player_channel_ids = {ch.channel_id for ch in player_channels}
            
            # 构造频道列表
            channel_list = []
            for channel in all_channels:
                channel_dict = channel.to_dict()
                channel_dict["is_subscribed"] = channel.channel_id in player_channel_ids
                channel_list.append(channel_dict)
            
            return {
                "success": True,
                "channels": channel_list,
                "subscribed_count": len(player_channels),
                "total_count": len(all_channels)
            }
            
        except Exception as e:
            self._logger.error(f"获取频道列表失败: {e}, player: {player_id}")
            return {
                "success": False,
                "error": "获取频道列表失败",
                "error_code": "FETCH_FAILED"
            }
    
    async def delete_message(self, 
                           player_id: str,
                           message_id: str,
                           channel: str) -> Dict[str, Any]:
        """
        删除消息
        
        Args:
            player_id: 操作者ID
            message_id: 消息ID
            channel: 频道名称
            
        Returns:
            删除结果
        """
        try:
            # 这里可以添加权限检查，比如只有消息发送者或管理员能删除
            
            # 删除消息
            success = await self._message_storage.delete_message(message_id, channel)
            
            return {
                "success": success,
                "message_id": message_id
            }
            
        except Exception as e:
            self._logger.error(f"删除消息失败: {e}, player: {player_id}, message: {message_id}")
            return {
                "success": False,
                "error": "删除消息失败",
                "error_code": "DELETE_FAILED"
            }
    
    # ========== 私有方法 ==========
    
    async def _validate_message(self, 
                               sender_id: str,
                               chat_type: ChatType,
                               content: str,
                               channel: Optional[str],
                               receiver_id: Optional[str]) -> Dict[str, Any]:
        """验证消息基础信息"""
        # 检查内容长度
        if len(content) < self.MIN_MESSAGE_LENGTH:
            return {
                "success": False,
                "error": "消息内容不能为空",
                "error_code": "EMPTY_CONTENT"
            }
        
        if len(content) > self.MAX_MESSAGE_LENGTH:
            return {
                "success": False,
                "error": f"消息内容超过{self.MAX_MESSAGE_LENGTH}字符限制",
                "error_code": "CONTENT_TOO_LONG"
            }
        
        # 检查私聊参数
        if chat_type == ChatType.PRIVATE:
            if not receiver_id:
                return {
                    "success": False,
                    "error": "私聊必须指定接收者",
                    "error_code": "MISSING_RECEIVER"
                }
            
            if receiver_id == sender_id:
                return {
                    "success": False,
                    "error": "不能给自己发私聊",
                    "error_code": "SELF_MESSAGE"
                }
        
        # 检查频道参数
        elif chat_type in (ChatType.WORLD, ChatType.CHANNEL):
            if not channel:
                return {
                    "success": False,
                    "error": "频道消息必须指定频道",
                    "error_code": "MISSING_CHANNEL"
                }
        
        return {"success": True}
    
    async def _check_rate_limit(self, player_id: str) -> bool:
        """检查发送速率限制"""
        current_time = time.time()
        
        # 获取玩家的发送记录
        if player_id not in self._rate_limits:
            self._rate_limits[player_id] = []
        
        timestamps = self._rate_limits[player_id]
        
        # 清理过期的时间戳
        cutoff_time = current_time - self.RATE_LIMIT_WINDOW
        timestamps[:] = [t for t in timestamps if t > cutoff_time]
        
        # 检查是否超过限制
        return len(timestamps) < self.MAX_MESSAGES_PER_MINUTE
    
    def _update_rate_limit(self, player_id: str) -> None:
        """更新速率限制记录"""
        current_time = time.time()
        
        if player_id not in self._rate_limits:
            self._rate_limits[player_id] = []
        
        self._rate_limits[player_id].append(current_time)
    
    async def _check_channel_access(self, player_id: str, channel: str) -> bool:
        """检查频道访问权限"""
        # 对于世界频道和系统频道，所有人都可以访问
        if channel in ("world", "system"):
            return True
        
        # 对于私人频道，需要检查订阅状态
        channel_id = await self._find_channel_by_name(channel)
        if not channel_id:
            return False
        
        return self._channel_manager.is_player_subscribed(player_id, channel_id)
    
    async def _find_channel_by_name(self, channel_name: str) -> Optional[str]:
        """根据频道名称查找频道ID"""
        all_channels = await self._channel_manager.get_all_channels()
        
        for channel in all_channels:
            if channel.channel_name == channel_name:
                return channel.channel_id
        
        return None
    
    def _get_default_channel(self, chat_type: ChatType) -> str:
        """获取默认频道名称"""
        if chat_type == ChatType.WORLD:
            return "world"
        elif chat_type == ChatType.SYSTEM:
            return "system"
        elif chat_type == ChatType.PRIVATE:
            return "private"
        else:
            return "general"


# 全局实例
_chat_handler: Optional[ChatHandler] = None


async def get_chat_handler() -> ChatHandler:
    """获取聊天处理器实例"""
    global _chat_handler
    if _chat_handler is None:
        _chat_handler = ChatHandler()
        await _chat_handler.initialize()
    return _chat_handler