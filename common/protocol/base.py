"""
Protocol base module - integration layer for tests
作者: lx
日期: 2025-06-18
"""

# Import core classes that tests expect
from .core.base_request import BaseRequest
from .core.base_response import BaseResponse
from .encoding.message_pool import (
    MessagePool, BufferPool, get_pool_stats, 
    create_request_batch, create_response_batch
)

__all__ = [
    "BaseRequest",
    "BaseResponse", 
    "MessagePool",
    "BufferPool",
    "get_pool_stats",
    "create_request_batch",
    "create_response_batch"
]