"""
Protocol Buffer协议层
作者: lx
日期: 2025-06-18
"""

from .core.message_type import MessageType
from .core.decorators import message, MESSAGE_REGISTRY
from .core.base_request import BaseRequest
from .core.base_response import BaseResponse

__all__ = [
    "MessageType",
    "message", 
    "MESSAGE_REGISTRY",
    "BaseRequest",
    "BaseResponse"
]