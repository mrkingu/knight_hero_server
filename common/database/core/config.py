"""
数据库配置
定义数据库连接和行为配置
作者: lx
日期: 2025-06-20
"""
from typing import Dict, Any

class DatabaseConfig:
    """数据库配置类"""
    
    # Redis配置
    REDIS_CONFIG = {
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "password": None,
        "pool_size": 100,
        "decode_responses": True
    }
    
    # MongoDB配置
    MONGO_CONFIG = {
        "uri": "mongodb://localhost:27017",
        "database": "game_db",
        "max_pool_size": 100,
        "min_pool_size": 10
    }
    
    # 缓存配置
    CACHE_CONFIG = {
        "default_ttl": 300,  # 5分钟
        "max_ttl": 3600,     # 1小时
        "ttl_variance": 0.2   # ±20%随机
    }
    
    # 并发配置
    CONCURRENT_CONFIG = {
        "queue_size": 1000,
        "batch_size": 10,
        "batch_timeout": 0.01  # 10ms
    }