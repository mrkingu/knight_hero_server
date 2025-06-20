"""
聊天请求消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_request import BaseRequest
from ...core.decorators import message
from ...core.message_type import MessageType

@message(MessageType.CHAT_REQUEST)
class ChatRequest(BaseRequest):
    """聊天请求"""
    
    def __init__(self):
        super().__init__()
        self.channel: str = "world"  # 聊天频道
        self.content: str = ""  # 聊天内容
        self.target_player_id: str = ""  # 私聊目标，为空则为公共频道