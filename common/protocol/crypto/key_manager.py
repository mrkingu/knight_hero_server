"""
密钥管理器
作者: lx
日期: 2025-06-18
"""
import os
from typing import Dict, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class KeyManager:
    """密钥管理器"""
    
    def __init__(self):
        self._keys: Dict[str, bytes] = {}
        
    def generate_key(self, key_id: str, size: int = 16) -> bytes:
        """生成密钥"""
        key = os.urandom(size)
        self._keys[key_id] = key
        return key
        
    def derive_key(self, password: bytes, salt: bytes, key_id: str, length: int = 16) -> bytes:
        """从密码派生密钥"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password)
        self._keys[key_id] = key
        return key
        
    def get_key(self, key_id: str) -> Optional[bytes]:
        """获取密钥"""
        return self._keys.get(key_id)
        
    def set_key(self, key_id: str, key: bytes):
        """设置密钥"""
        self._keys[key_id] = key
        
    def remove_key(self, key_id: str) -> bool:
        """删除密钥"""
        return self._keys.pop(key_id, None) is not None