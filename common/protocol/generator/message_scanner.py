"""
消息扫描器
作者: lx
日期: 2025-06-18
"""
from pathlib import Path
from typing import List, Dict, Any
from ..core.decorators import MESSAGE_REGISTRY

class MessageScanner:
    """消息类扫描器"""
    
    def __init__(self, search_paths: List[str]):
        self.search_paths = [Path(p) for p in search_paths]
        
    def scan_registered_messages(self) -> Dict[int, Any]:
        """扫描已注册的消息类"""
        return dict(MESSAGE_REGISTRY)
        
    def get_message_info(self, msg_type: int) -> Dict[str, Any]:
        """获取消息信息"""
        msg_class = MESSAGE_REGISTRY.get(msg_type)
        if not msg_class:
            return {}
            
        info = {
            "name": msg_class.__name__,
            "type": msg_type,
            "module": msg_class.__module__,
            "fields": []
        }
        
        # 获取类的字段信息
        if hasattr(msg_class, '__annotations__'):
            for field_name, field_type in msg_class.__annotations__.items():
                info["fields"].append({
                    "name": field_name,
                    "type": str(field_type)
                })
                
        return info
        
    def scan_all_messages(self) -> List[Dict[str, Any]]:
        """扫描所有消息"""
        messages = []
        for msg_type, msg_class in MESSAGE_REGISTRY.items():
            messages.append(self.get_message_info(msg_type))
        return messages