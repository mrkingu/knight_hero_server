"""
登录响应消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_response import BaseResponse
from ...core.decorators import message
from ...core.message_type import MessageType
from typing import Optional, Dict, Any

@message(MessageType.LOGIN_RESPONSE)
class LoginResponse(BaseResponse):
    """登录响应"""
    
    def __init__(self):
        super().__init__()
        self.player_id: Optional[str] = None  # 玩家ID
        self.token: Optional[str] = None  # 会话令牌
        self.server_time: int = 0  # 服务器时间
        self.player_info: Optional[Dict[str, Any]] = None  # 玩家信息