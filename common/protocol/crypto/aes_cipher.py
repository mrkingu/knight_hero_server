"""
AES加密器
使用AES-128-GCM进行加密
作者: lx
日期: 2025-06-18
"""
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class AESCipher:
    """AES-GCM加密器"""
    
    def __init__(self, key: Optional[bytes] = None):
        self.key = key or os.urandom(16)  # 128位密钥
        self.backend = default_backend()
        
    def encrypt(self, plaintext: bytes) -> bytes:
        """加密数据"""
        # 生成随机IV
        iv = os.urandom(12)  # GCM推荐96位IV
        
        # 创建加密器
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv),
            backend=self.backend
        )
        encryptor = cipher.encryptor()
        
        # 加密
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        # 返回 IV + 认证标签 + 密文
        return iv + encryptor.tag + ciphertext
        
    def decrypt(self, ciphertext: bytes) -> bytes:
        """解密数据"""
        # 提取IV、认证标签和密文
        iv = ciphertext[:12]
        tag = ciphertext[12:28]
        actual_ciphertext = ciphertext[28:]
        
        # 创建解密器
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv, tag),
            backend=self.backend
        )
        decryptor = cipher.decryptor()
        
        # 解密
        return decryptor.update(actual_ciphertext) + decryptor.finalize()