"""
序列化工具
作者: lx
日期: 2025-06-18
"""
import msgpack
import json
from typing import Any, Dict

def serialize_msgpack(data: Any) -> bytes:
    """使用msgpack序列化"""
    return msgpack.packb(data)

def deserialize_msgpack(data: bytes) -> Any:
    """使用msgpack反序列化"""
    return msgpack.unpackb(data, raw=False)

def serialize_json(data: Any) -> bytes:
    """使用JSON序列化"""
    return json.dumps(data, ensure_ascii=False).encode('utf-8')

def deserialize_json(data: bytes) -> Any:
    """使用JSON反序列化"""
    return json.loads(data.decode('utf-8'))

def serialize_protobuf(message) -> bytes:
    """序列化Protobuf消息"""
    if hasattr(message, 'SerializeToString'):
        return message.SerializeToString()
    else:
        raise ValueError("Object is not a protobuf message")

def auto_serialize(data: Any, format: str = "msgpack") -> bytes:
    """自动选择序列化格式"""
    if format == "msgpack":
        return serialize_msgpack(data)
    elif format == "json":
        return serialize_json(data)
    elif format == "protobuf":
        return serialize_protobuf(data)
    else:
        raise ValueError(f"Unsupported format: {format}")

def auto_deserialize(data: bytes, format: str = "msgpack") -> Any:
    """自动选择反序列化格式"""
    if format == "msgpack":
        return deserialize_msgpack(data)
    elif format == "json":
        return deserialize_json(data)
    else:
        raise ValueError(f"Unsupported format: {format}")