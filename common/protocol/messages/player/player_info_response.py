"""
玩家信息响应消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_response import BaseResponse
from ...core.decorators import message
from ...core.message_type import MessageType
from typing import Optional, Dict, Any

@message(MessageType.PLAYER_INFO_RESPONSE)
class PlayerInfoResponse(BaseResponse):
    """玩家信息响应"""
    
    def __init__(self):
        super().__init__()
        self.player_info: Optional[Dict[str, Any]] = None  # 玩家详细信息