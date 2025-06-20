"""
请求基类
所有请求消息的基类
作者: lx
日期: 2025-06-18
"""
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class BaseRequest:
    """请求消息基类"""
    
    MESSAGE_TYPE: int = 0  # 由装饰器设置
    
    def __init__(self, player_id: Optional[str] = None, payload: Optional[bytes] = None, msg_id: Optional[int] = None):
        # 消息头
        self.sequence: int = int(uuid.uuid4().int & 0xFFFFFFFF)  # 序列号
        self.timestamp: int = int(datetime.now().timestamp() * 1000)  # 时间戳(毫秒)
        self.player_id: Optional[str] = player_id  # 玩家ID
        
        # 消息内容 - 兼容测试接口
        self.payload: Optional[bytes] = payload
        self.msg_id: Optional[int] = msg_id or getattr(self, 'MESSAGE_TYPE', 0)
        
        # 元数据
        self.metadata: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "msg_type": self.MESSAGE_TYPE,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }
        
        if self.player_id:
            data["player_id"] = self.player_id
            
        if self.payload:
            data["payload"] = self.payload
            
        if self.msg_id:
            data["msg_id"] = self.msg_id
            
        if self.metadata:
            data["metadata"] = self.metadata
            
        # 添加子类字段
        for key, value in self.__dict__.items():
            if key not in data and not key.startswith("_"):
                data[key] = value
                
        return data
        
    def from_dict(self, data: Dict[str, Any]) -> "BaseRequest":
        """从字典创建"""
        self.sequence = data.get("sequence", int(uuid.uuid4().int & 0xFFFFFFFF))
        self.timestamp = data.get("timestamp", int(datetime.now().timestamp() * 1000))
        self.player_id = data.get("player_id")
        self.payload = data.get("payload")
        self.msg_id = data.get("msg_id")
        self.metadata = data.get("metadata", {})
        
        # 设置子类字段
        for key, value in data.items():
            if hasattr(self, key) and key not in ["sequence", "timestamp", "player_id", "metadata", "payload", "msg_id"]:
                setattr(self, key, value)
                
        return self
        
    async def to_bytes(self) -> bytes:
        """序列化为字节"""
        import msgpack
        return msgpack.packb(self.to_dict())
        
    @classmethod
    def from_bytes(cls, data: bytes) -> "BaseRequest":
        """从字节反序列化"""
        import msgpack
        dict_data = msgpack.unpackb(data, raw=False)
        instance = cls()
        return instance.from_dict(dict_data)
        
    def validate(self) -> bool:
        """验证消息有效性"""
        # 子类可以重写此方法添加自定义验证
        return True