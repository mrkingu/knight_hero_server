"""
消息类型定义
定义所有消息号，正数为请求，负数为响应
作者: lx
日期: 2025-06-18
"""
from enum import IntEnum

class MessageType(IntEnum):
    """消息类型枚举"""
    
    # 系统消息 (1-999)
    HEARTBEAT_REQUEST = 1
    HEARTBEAT_RESPONSE = -1
    
    # 认证消息 (1000-1999)
    LOGIN_REQUEST = 1001
    LOGIN_RESPONSE = -1001
    LOGOUT_REQUEST = 1002
    LOGOUT_RESPONSE = -1002
    REGISTER_REQUEST = 1003
    REGISTER_RESPONSE = -1003
    
    # 玩家消息 (2000-2999)
    PLAYER_INFO_REQUEST = 2001
    PLAYER_INFO_RESPONSE = -2001
    UPDATE_PLAYER_REQUEST = 2002
    UPDATE_PLAYER_RESPONSE = -2002
    
    # 聊天消息 (3000-3999)
    CHAT_REQUEST = 3001
    CHAT_RESPONSE = -3001
    CHAT_HISTORY_REQUEST = 3002
    CHAT_HISTORY_RESPONSE = -3002
    
    # 战斗消息 (4000-4999)
    BATTLE_START_REQUEST = 4001
    BATTLE_START_RESPONSE = -4001
    BATTLE_END_REQUEST = 4002
    BATTLE_END_RESPONSE = -4002
    
    @classmethod
    def get_response_type(cls, request_type: int) -> int:
        """获取请求对应的响应类型"""
        return -abs(request_type)
        
    @classmethod
    def is_request(cls, msg_type: int) -> bool:
        """判断是否为请求消息"""
        return msg_type > 0
        
    @classmethod
    def is_response(cls, msg_type: int) -> bool:
        """判断是否为响应消息"""
        return msg_type < 0