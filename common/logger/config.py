"""
日志配置
Logger Configuration

作者: lx
日期: 2025-06-18
描述: 日志系统配置管理
"""

import os
from pathlib import Path
from typing import Dict, Any


# 默认日志目录
DEFAULT_LOG_DIR = Path("logs")

# 确保日志目录存在
DEFAULT_LOG_DIR.mkdir(exist_ok=True)


# 日志配置
LOG_CONFIG: Dict[str, Dict[str, Any]] = {
    "player": {
        "level": "INFO",
        "queue_size": 10000,
        "batch_size": 100,
        "batch_timeout": 1.0,
        "handlers": [
            {
                "type": "rotating_file",
                "filename": DEFAULT_LOG_DIR / "player.log",
                "max_bytes": 100 * 1024 * 1024,  # 100MB
                "backup_count": 10,
                "compress": True,
                "level": "INFO",
                "formatter": {
                    "type": "json",
                    "timestamp_format": "%Y-%m-%d %H:%M:%S.%f",
                    "ensure_ascii": False
                }
            },
            {
                "type": "console",
                "level": "WARNING",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [PLAYER] {message}",
                    "include_extra": True
                }
            }
        ]
    },
    
    "battle": {
        "level": "INFO",
        "queue_size": 15000,
        "batch_size": 200,
        "batch_timeout": 0.5,
        "handlers": [
            {
                "type": "timed_rotating_file",
                "filename": DEFAULT_LOG_DIR / "battle.log",
                "when": "midnight",
                "interval": 1,
                "backup_count": 7,
                "compress": True,
                "level": "INFO",
                "formatter": {
                    "type": "json",
                    "timestamp_format": "%Y-%m-%d %H:%M:%S.%f",
                    "ensure_ascii": False
                }
            }
        ]
    },
    
    "system": {
        "level": "INFO",
        "queue_size": 5000,
        "batch_size": 50,
        "batch_timeout": 2.0,
        "handlers": [
            {
                "type": "rotating_file",
                "filename": DEFAULT_LOG_DIR / "system.log",
                "max_bytes": 50 * 1024 * 1024,  # 50MB
                "backup_count": 5,
                "compress": True,
                "level": "INFO",
                "formatter": {
                    "type": "json",
                    "timestamp_format": "%Y-%m-%d %H:%M:%S.%f",
                    "ensure_ascii": False
                }
            },
            {
                "type": "console",
                "level": "INFO",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [SYSTEM] {message}",
                    "include_extra": True
                }
            }
        ]
    },
    
    "error": {
        "level": "ERROR",
        "queue_size": 5000,
        "batch_size": 10,
        "batch_timeout": 0.1,
        "handlers": [
            {
                "type": "rotating_file",
                "filename": DEFAULT_LOG_DIR / "error.log",
                "max_bytes": 100 * 1024 * 1024,  # 100MB
                "backup_count": 20,
                "compress": True,
                "level": "ERROR",
                "formatter": {
                    "type": "json",
                    "timestamp_format": "%Y-%m-%d %H:%M:%S.%f",
                    "ensure_ascii": False,
                    "fields": {
                        "trace_id": "trace_id",
                        "user_id": "user_id",
                        "request_id": "request_id"
                    }
                }
            },
            {
                "type": "console",
                "level": "ERROR",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [ERROR] {message}",
                    "include_extra": True
                }
            }
        ]
    },
    
    "debug": {
        "level": "DEBUG",
        "queue_size": 2000,
        "batch_size": 20,
        "batch_timeout": 5.0,
        "handlers": [
            {
                "type": "file",
                "filename": DEFAULT_LOG_DIR / "debug.log",
                "level": "DEBUG",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [{name}] {funcName}:{lineno} - {message}",
                    "include_extra": True
                }
            }
        ]
    }
}


# 开发环境配置
DEVELOPMENT_CONFIG: Dict[str, Dict[str, Any]] = {
    "player": {
        **LOG_CONFIG["player"],
        "level": "DEBUG",
        "handlers": [
            {
                "type": "console",
                "level": "DEBUG",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [PLAYER] {message}",
                    "include_extra": True
                }
            }
        ]
    },
    
    "battle": {
        **LOG_CONFIG["battle"],
        "level": "DEBUG",
        "handlers": [
            {
                "type": "console",
                "level": "DEBUG",
                "formatter": {
                    "type": "simple",
                    "format": "[{asctime}] {levelname:8} [BATTLE] {message}",
                    "include_extra": True
                }
            }
        ]
    },
    
    "system": {
        **LOG_CONFIG["system"],
        "level": "DEBUG"
    },
    
    "error": {
        **LOG_CONFIG["error"],
        "level": "WARNING"
    }
}


def get_config(environment: str = "production") -> Dict[str, Dict[str, Any]]:
    """
    获取指定环境的日志配置
    
    Args:
        environment: 环境名称 ("production", "development")
        
    Returns:
        日志配置字典
    """
    if environment.lower() == "development":
        return DEVELOPMENT_CONFIG
    else:
        return LOG_CONFIG


def update_config_from_env() -> None:
    """从环境变量更新配置"""
    # 可以通过环境变量覆盖默认配置
    log_level = os.getenv("LOG_LEVEL")
    if log_level:
        for logger_config in LOG_CONFIG.values():
            logger_config["level"] = log_level.upper()
    
    log_dir = os.getenv("LOG_DIR")
    if log_dir:
        global DEFAULT_LOG_DIR
        DEFAULT_LOG_DIR = Path(log_dir)
        DEFAULT_LOG_DIR.mkdir(exist_ok=True)
        
        # 更新所有文件路径
        for logger_config in LOG_CONFIG.values():
            for handler in logger_config["handlers"]:
                if "filename" in handler:
                    filename = Path(handler["filename"]).name
                    handler["filename"] = DEFAULT_LOG_DIR / filename


# 启动时更新配置
update_config_from_env()