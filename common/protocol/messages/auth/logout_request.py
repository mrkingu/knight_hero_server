"""
登出请求消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_request import BaseRequest
from ...core.decorators import message
from ...core.message_type import MessageType

@message(MessageType.LOGOUT_REQUEST)
class LogoutRequest(BaseRequest):
    """登出请求"""
    
    def __init__(self):
        super().__init__()
        self.reason: str = "normal"  # 登出原因