"""
加密配置
作者: lx
日期: 2025-06-18
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class CryptoConfig:
    """加密配置"""
    enabled: bool = False
    algorithm: str = "AES-128-GCM"
    key_size: int = 16
    key_rotation_interval: int = 3600  # 密钥轮换间隔(秒)
    compression_threshold: int = 128  # 压缩阈值(字节)
    
    @classmethod
    def default(cls) -> "CryptoConfig":
        """默认配置"""
        return cls()
        
    @classmethod
    def secure(cls) -> "CryptoConfig":
        """安全配置"""
        return cls(
            enabled=True,
            algorithm="AES-128-GCM",
            key_size=16,
            key_rotation_interval=1800,  # 30分钟轮换
            compression_threshold=64
        )