"""
聊天消息数据模型
Chat Message Data Models

作者: lx
日期: 2025-06-18
描述: 聊天消息相关的数据模型定义
"""
from typing import Dict, Any, Optional, List
from enum import IntEnum
from pydantic import BaseModel, Field
from datetime import datetime
import orjson


class ChatType(IntEnum):
    """聊天类型枚举"""
    WORLD = 1       # 世界聊天
    PRIVATE = 2     # 私聊
    CHANNEL = 3     # 频道聊天
    SYSTEM = 4      # 系统消息


class MessageStatus(IntEnum):
    """消息状态枚举"""
    PENDING = 0     # 待发送
    SENT = 1        # 已发送
    READ = 2        # 已读
    DELETED = 3     # 已删除


class ChatMessage(BaseModel):
    """聊天消息模型"""
    
    # 基础信息
    message_id: str = Field(..., description="消息ID")
    chat_type: ChatType = Field(..., description="聊天类型")
    channel: str = Field(..., description="频道名称")
    
    # 发送者信息
    sender_id: str = Field(..., description="发送者ID")
    sender_name: str = Field(..., description="发送者昵称")
    
    # 接收者信息（私聊时使用）
    receiver_id: Optional[str] = Field(default=None, description="接收者ID")
    receiver_name: Optional[str] = Field(default=None, description="接收者昵称")
    
    # 消息内容
    content: str = Field(..., description="消息内容")
    original_content: Optional[str] = Field(default=None, description="原始内容（过滤前）")
    
    # 时间信息
    timestamp: float = Field(..., description="消息时间戳")
    created_at: Optional[datetime] = Field(default=None, description="创建时间")
    
    # 状态信息
    status: MessageStatus = Field(default=MessageStatus.PENDING, description="消息状态")
    
    # 扩展信息
    extra_data: Optional[Dict[str, Any]] = Field(default=None, description="扩展数据")
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        data = self.model_dump()
        # 处理datetime类型
        if data.get('created_at'):
            data['created_at'] = data['created_at'].isoformat()
        return orjson.dumps(data).decode('utf-8')
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ChatMessage':
        """从JSON字符串创建消息"""
        data = orjson.loads(json_str)
        # 处理datetime类型
        if data.get('created_at') and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class OfflineMessage(BaseModel):
    """离线消息模型"""
    
    # 基础信息
    offline_id: str = Field(..., description="离线消息ID")
    player_id: str = Field(..., description="玩家ID")
    message: ChatMessage = Field(..., description="聊天消息")
    
    # 时间信息
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    expire_at: Optional[datetime] = Field(default=None, description="过期时间")
    
    # 状态信息
    is_read: bool = Field(default=False, description="是否已读")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class ChannelInfo(BaseModel):
    """频道信息模型"""
    
    # 基础信息
    channel_id: str = Field(..., description="频道ID")
    channel_name: str = Field(..., description="频道名称")
    channel_type: ChatType = Field(..., description="频道类型")
    
    # 描述信息
    description: Optional[str] = Field(default=None, description="频道描述")
    
    # 管理信息
    creator_id: str = Field(..., description="创建者ID")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    
    # 成员信息
    member_count: int = Field(default=0, description="成员数量")
    max_members: int = Field(default=1000, description="最大成员数")
    
    # 状态信息
    is_active: bool = Field(default=True, description="是否活跃")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class ChatStatistics(BaseModel):
    """聊天统计信息模型"""
    
    # 消息统计
    total_messages: int = Field(default=0, description="总消息数")
    today_messages: int = Field(default=0, description="今日消息数")
    
    # 频道统计
    active_channels: int = Field(default=0, description="活跃频道数")
    total_channels: int = Field(default=0, description="总频道数")
    
    # 用户统计
    online_users: int = Field(default=0, description="在线用户数")
    active_users: int = Field(default=0, description="活跃用户数")
    
    # 时间信息
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()