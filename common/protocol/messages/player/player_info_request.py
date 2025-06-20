"""
玩家信息请求消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_request import BaseRequest
from ...core.decorators import message
from ...core.message_type import MessageType

@message(MessageType.PLAYER_INFO_REQUEST)
class PlayerInfoRequest(BaseRequest):
    """玩家信息请求"""
    
    def __init__(self):
        super().__init__()
        self.target_player_id: str = ""  # 目标玩家ID，为空则查询自己