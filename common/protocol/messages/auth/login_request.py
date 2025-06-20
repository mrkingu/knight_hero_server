"""
登录请求消息
作者: lx
日期: 2025-06-18
"""
from ...core.base_request import BaseRequest
from ...core.decorators import message
from ...core.message_type import MessageType

@message(MessageType.LOGIN_REQUEST)
class LoginRequest(BaseRequest):
    """登录请求"""
    
    def __init__(self):
        super().__init__()
        self.username: str = ""  # 用户名
        self.password: str = ""  # 密码(已加密)
        self.device_id: str = ""  # 设备ID
        self.platform: str = ""  # 平台(ios/android/web)
        self.version: str = ""  # 客户端版本
        
    def validate(self) -> bool:
        """验证请求有效性"""
        if not self.username or not self.password:
            return False
        if not self.device_id or not self.platform:
            return False
        return True