"""
文档基类
所有MongoDB文档的基类
作者: lx
日期: 2025-06-20
"""
from beanie import Document
from datetime import datetime
from typing import Optional

class BaseDocument(Document):
    """文档基类"""
    
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
    version: int = 1
    
    class Settings:
        """Beanie设置"""
        use_state_management = True
        
    async def save(self, **kwargs):
        """保存前更新时间戳"""
        self.updated_at = datetime.now()
        self.version += 1
        return await super().save(**kwargs)