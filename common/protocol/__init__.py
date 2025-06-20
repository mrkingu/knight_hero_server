"""
通信协议模块
Communication Protocol Module

作者: lx
日期: 2025-06-18
描述: 定义客户端与服务器之间的通信协议
"""

from .base import BaseRequest, BaseResponse, get_pool_stats
from .protocol_utils import ProtocolUtils, MessageBuffer, Encryption, MessageFramer, quick_encode, quick_decode
from .proto_gen import AutoProtoGenerator, TypeMapping

__all__ = [
    # 基础消息类
    'BaseRequest',
    'BaseResponse', 
    'get_pool_stats',
    
    # 协议工具类
    'ProtocolUtils',
    'MessageBuffer',
    'Encryption',
    'MessageFramer',
    'quick_encode',
    'quick_decode',
    
    # Proto生成工具
    'AutoProtoGenerator',
    'TypeMapping',
]