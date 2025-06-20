"""
响应基类
所有响应消息的基类
作者: lx
日期: 2025-06-18
"""
from typing import Optional, Dict, Any
from datetime import datetime

class BaseResponse:
    """响应消息基类"""
    
    MESSAGE_TYPE: int = 0  # 由装饰器设置
    
    def __init__(self, code: int = 0, message: str = "Success", payload: Optional[bytes] = None, msg_id: Optional[int] = None):
        # 响应状态
        self.code: int = code  # 0表示成功，其他为错误码
        self.message: str = message  # 响应消息
        
        # 响应头
        self.sequence: Optional[str] = None  # 对应请求的序列号
        self.timestamp: int = int(datetime.now().timestamp() * 1000)  # 时间戳(毫秒)
        
        # 消息内容 - 兼容测试接口
        self.payload: Optional[bytes] = payload
        self.msg_id: Optional[int] = msg_id or getattr(self, 'MESSAGE_TYPE', 0)
        
        # 响应数据
        self.data: Optional[Dict[str, Any]] = None
        
    @classmethod
    def success(cls, payload: Optional[bytes] = None, request_sequence: Optional[str] = None, msg_id: Optional[int] = None) -> "BaseResponse":
        """创建成功响应"""
        response = cls(code=0, message="Success", payload=payload, msg_id=msg_id)
        if request_sequence is not None:
            response.sequence = request_sequence
        return response
        
    @classmethod
    def error(cls, code: int, message: str, request_sequence: Optional[str] = None, msg_id: Optional[int] = None) -> "BaseResponse":
        """创建错误响应"""
        response = cls(code=code, message=message, msg_id=msg_id)
        if request_sequence is not None:
            response.sequence = request_sequence
        return response
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "msg_type": self.MESSAGE_TYPE,
            "code": self.code,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        
        if self.sequence:
            data["sequence"] = self.sequence
            
        if self.payload:
            data["payload"] = self.payload
            
        if self.msg_id:
            data["msg_id"] = self.msg_id
            
        if self.data:
            data["data"] = self.data
            
        # 添加子类字段
        for key, value in self.__dict__.items():
            if key not in data and not key.startswith("_") and key not in ["code", "message", "data", "payload", "msg_id"]:
                data[key] = value
                
        return data
        
    def from_dict(self, data: Dict[str, Any]) -> "BaseResponse":
        """从字典创建"""
        self.code = data.get("code", 0)
        self.message = data.get("message", "Success")
        self.sequence = data.get("sequence")
        self.timestamp = data.get("timestamp", int(datetime.now().timestamp() * 1000))
        self.payload = data.get("payload")
        self.msg_id = data.get("msg_id")
        self.data = data.get("data")
        
        # 设置子类字段
        for key, value in data.items():
            if hasattr(self, key) and key not in ["code", "message", "sequence", "timestamp", "data", "payload", "msg_id"]:
                setattr(self, key, value)
                
        return self
        
    async def to_bytes(self) -> bytes:
        """序列化为字节"""
        import msgpack
        return msgpack.packb(self.to_dict())
        
    @classmethod
    def from_bytes(cls, data: bytes) -> "BaseResponse":
        """从字节反序列化"""
        import msgpack
        dict_data = msgpack.unpackb(data, raw=False)
        instance = cls()
        return instance.from_dict(dict_data)