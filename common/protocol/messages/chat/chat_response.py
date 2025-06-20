"""
聊天响应消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_response import BaseResponse
from ...core.decorators import message
from ...core.message_type import MessageType

@message(MessageType.CHAT_RESPONSE)
class ChatResponse(BaseResponse):
    """聊天响应"""
    
    def __init__(self):
        super().__init__()
        self.message_id: str = ""  # 消息ID
        self.broadcast_count: int = 0  # 广播人数