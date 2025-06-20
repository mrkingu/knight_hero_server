"""
协议装饰器
用于自动绑定消息号和注册消息类
作者: lx
日期: 2025-06-18
"""
from typing import Type, Dict, Any
from functools import wraps

# 全局消息注册表
MESSAGE_REGISTRY: Dict[int, Type] = {}

def message(msg_type: int):
    """
    消息装饰器，用于绑定消息号
    
    使用示例:
    @message(MessageType.LOGIN_REQUEST)
    class LoginRequest(BaseRequest):
        pass
    """
    def decorator(cls: Type) -> Type:
        # 设置消息类型
        cls.MESSAGE_TYPE = msg_type
        
        # 注册到全局注册表
        if msg_type in MESSAGE_REGISTRY:
            raise ValueError(f"Message type {msg_type} already registered")
        MESSAGE_REGISTRY[msg_type] = cls
        
        # 添加工厂方法
        @classmethod
        def create(cls, **kwargs):
            """创建消息实例"""
            instance = cls()
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            return instance
            
        cls.create = create
        
        return cls
        
    return decorator

def field(required: bool = False, default: Any = None, description: str = ""):
    """
    字段装饰器，用于定义消息字段
    
    使用示例:
    @field(required=True, description="用户名")
    username: str
    """
    def decorator(func):
        func._field_metadata = {
            "required": required,
            "default": default,
            "description": description
        }
        return func
    return decorator