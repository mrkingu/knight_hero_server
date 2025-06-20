"""
消息元数据
作者: lx  
日期: 2025-06-18
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class MessageMeta:
    """消息元数据"""
    msg_type: int
    msg_size: int
    compression: bool = False
    encryption: bool = False
    checksum: Optional[str] = None
    version: str = "1.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "msg_type": self.msg_type,
            "msg_size": self.msg_size,
            "compression": self.compression,
            "encryption": self.encryption,
            "checksum": self.checksum,
            "version": self.version
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageMeta":
        """从字典创建"""
        return cls(
            msg_type=data["msg_type"],
            msg_size=data["msg_size"],
            compression=data.get("compression", False),
            encryption=data.get("encryption", False),
            checksum=data.get("checksum"),
            version=data.get("version", "1.0")
        )