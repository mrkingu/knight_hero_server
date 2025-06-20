"""
文档基类
所有MongoDB文档的基类，只包含基础字段
作者: mrkingu
日期: 2025-06-20
"""
from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional, Dict, Any

class BaseDocument(Document):
    """基础文档类 - 只包含数据定义"""
    
    # 基础字段
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    version: int = Field(default=1, description="版本号")
    is_deleted: bool = Field(default=False, description="软删除标记")
    
    class Settings:
        """Beanie设置"""
        use_state_management = True
        
    class Config:
        """Pydantic配置"""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        
    class Meta:
        """元数据配置 - 供Repository生成器使用"""
        # 定义支持并发操作的字段
        concurrent_fields: Dict[str, Dict[str, Any]] = {}
        # 索引定义
        indexes: list = []
        # 缓存策略
        cache_ttl: int = 300  # 默认5分钟
        # 是否启用软删除
        soft_delete: bool = True