"""
配置管理模块
Configuration Module

作者: lx
日期: 2025-06-18
描述: 系统配置文件加载和管理，包含Excel转JSON工具、自动配置类生成、配置加载器
"""

from .base_config import (
    BaseConfig, ItemConfig, SkillConfig, NpcConfig,
    ConfigManager, config_manager, get_config_manager
)
from .excel_to_json import (
    ExcelToJsonConverter, create_sample_excel_files
)
from .config_gen import (
    ConfigClassGenerator
)
from .config_loader import (
    ConfigLoader, config_loader, get_config_loader, initialize_configs
)

__all__ = [
    # 基础配置类
    'BaseConfig',
    'ItemConfig', 
    'SkillConfig',
    'NpcConfig',
    'ConfigManager',
    'config_manager',
    'get_config_manager',
    
    # Excel转JSON工具
    'ExcelToJsonConverter',
    'create_sample_excel_files',
    
    # 配置类生成器
    'ConfigClassGenerator',
    
    # 配置加载器
    'ConfigLoader',
    'config_loader',
    'get_config_loader',
    'initialize_configs'
]