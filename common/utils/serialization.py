"""
统一序列化工具
作者: lx
日期: 2025-06-20
"""
import msgpack
import json
from typing import Any, Dict

# 导入现有的序列化方法以保持兼容性
from ..protocol.utils.serializer import (
    serialize_msgpack, deserialize_msgpack,
    serialize_json, deserialize_json,
    serialize_protobuf
)

def auto_serialize(data: Any, format: str = "msgpack") -> bytes:
    """
    自动选择序列化格式
    
    Args:
        data: 要序列化的数据
        format: 序列化格式 ("msgpack", "json", "protobuf")
        
    Returns:
        序列化后的字节数据
    """
    if format == "msgpack":
        return serialize_msgpack(data)
    elif format == "json":
        return serialize_json(data)
    elif format == "protobuf":
        return serialize_protobuf(data)
    else:
        raise ValueError(f"Unsupported format: {format}")

def auto_deserialize(data: bytes, format: str = "msgpack") -> Any:
    """
    自动选择反序列化格式
    
    Args:
        data: 要反序列化的字节数据
        format: 反序列化格式 ("msgpack", "json")
        
    Returns:
        反序列化后的数据
    """
    if format == "msgpack":
        return deserialize_msgpack(data)
    elif format == "json":
        return deserialize_json(data)
    else:
        raise ValueError(f"Unsupported format: {format}")

# 为了向后兼容，也导出具体的序列化方法
__all__ = [
    'auto_serialize', 'auto_deserialize',
    'serialize_msgpack', 'deserialize_msgpack',
    'serialize_json', 'deserialize_json',
    'serialize_protobuf'
]