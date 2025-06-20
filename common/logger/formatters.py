"""
日志格式化器
Logger Formatters

作者: lx
日期: 2025-06-18
描述: 提供JSON和简单文本格式的日志格式化器
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional


class JSONFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    
    def __init__(
        self, 
        fields: Optional[Dict[str, str]] = None,
        timestamp_format: str = "%Y-%m-%d %H:%M:%S.%f",
        ensure_ascii: bool = False
    ):
        """
        初始化JSON格式化器
        
        Args:
            fields: 自定义字段映射
            timestamp_format: 时间戳格式
            ensure_ascii: 是否确保ASCII编码
        """
        super().__init__()
        self.fields = fields or {}
        self.timestamp_format = timestamp_format
        self.ensure_ascii = ensure_ascii
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录为JSON格式
        
        Args:
            record: 日志记录对象
            
        Returns:
            JSON格式的日志字符串
        """
        # 基本日志信息
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).strftime(self.timestamp_format),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread": record.thread,
            "thread_name": record.threadName,
        }
        
        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # 添加自定义字段
        for field_name, attr_name in self.fields.items():
            if hasattr(record, attr_name):
                log_data[field_name] = getattr(record, attr_name)
        
        # 添加额外的记录属性
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "getMessage", "exc_info",
                "exc_text", "stack_info", "taskName"
            }:
                extra_fields[key] = value
        
        if extra_fields:
            log_data["extra"] = extra_fields
        
        return json.dumps(log_data, ensure_ascii=self.ensure_ascii, default=str)


class SimpleFormatter(logging.Formatter):
    """简单文本格式化器"""
    
    def __init__(
        self,
        format_string: Optional[str] = None,
        date_format: Optional[str] = None,
        include_extra: bool = True
    ):
        """
        初始化简单格式化器
        
        Args:
            format_string: 自定义格式字符串
            date_format: 日期格式
            include_extra: 是否包含额外字段
        """
        if format_string is None:
            format_string = "[{asctime}] {levelname:8} [{name}] {message}"
        
        super().__init__(format_string, date_format, style="{")
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录为简单文本格式
        
        Args:
            record: 日志记录对象
            
        Returns:
            格式化的日志字符串
        """
        # 基本格式化
        formatted = super().format(record)
        
        # 添加额外字段
        if self.include_extra:
            extra_parts = []
            for key, value in record.__dict__.items():
                if key not in {
                    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                    "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
                    "thread", "threadName", "processName", "process", "getMessage", "exc_info",
                    "exc_text", "stack_info", "taskName", "asctime", "message"
                }:
                    extra_parts.append(f"{key}={value}")
            
            if extra_parts:
                formatted += " | " + " ".join(extra_parts)
        
        return formatted


class ColoredFormatter(SimpleFormatter):
    """彩色控制台格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色  
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化带颜色的日志记录
        
        Args:
            record: 日志记录对象
            
        Returns:
            带颜色的格式化日志字符串
        """
        # 获取基本格式化结果
        formatted = super().format(record)
        
        # 添加颜色
        color = self.COLORS.get(record.levelname, '')
        if color:
            # 只给级别名称添加颜色
            formatted = formatted.replace(
                f"{record.levelname:8}",
                f"{color}{record.levelname:8}{self.RESET}"
            )
        
        return formatted