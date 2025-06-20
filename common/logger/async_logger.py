"""
异步日志系统
Async Logger System

作者: lx
日期: 2025-06-18
描述: 高性能异步日志系统，支持批量写入和队列缓冲
"""

import asyncio
import logging
import time
from asyncio import Queue
from typing import Dict, List, Optional, Union, Any, Callable

from .handlers import (
    AsyncFileHandler, 
    AsyncConsoleHandler, 
    AsyncRotatingFileHandler,
    AsyncTimedRotatingFileHandler
)
from .formatters import JSONFormatter, SimpleFormatter


class LogRecord:
    """日志记录包装类"""
    
    def __init__(
        self,
        level: int,
        message: str,
        logger_name: str,
        timestamp: float,
        extra_data: Optional[Dict[str, Any]] = None
    ):
        """
        初始化日志记录
        
        Args:
            level: 日志级别
            message: 日志消息
            logger_name: 日志器名称
            timestamp: 时间戳
            extra_data: 额外数据
        """
        self.level = level
        self.message = message
        self.logger_name = logger_name
        self.timestamp = timestamp
        self.extra_data = extra_data or {}
    
    def to_logging_record(self) -> logging.LogRecord:
        """转换为标准日志记录对象"""
        record = logging.LogRecord(
            name=self.logger_name,
            level=self.level,
            pathname="",
            lineno=0,
            msg=self.message,
            args=(),
            exc_info=None
        )
        record.created = self.timestamp
        
        # 添加额外数据
        for key, value in self.extra_data.items():
            setattr(record, key, value)
        
        return record


class AsyncLogger:
    """异步日志器"""
    
    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
        queue_size: int = 10000,
        batch_size: int = 100,
        batch_timeout: float = 1.0,
        handlers: Optional[List[logging.Handler]] = None
    ):
        """
        初始化异步日志器
        
        Args:
            name: 日志器名称
            level: 日志级别
            queue_size: 队列大小
            batch_size: 批量处理大小
            batch_timeout: 批量处理超时时间（秒）
            handlers: 处理器列表
        """
        self.name = name
        self.level = level
        self.queue_size = queue_size
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.handlers: List[logging.Handler] = handlers or []
        
        # 创建队列和控制变量
        self.log_queue: Queue[Optional[LogRecord]] = Queue(maxsize=queue_size)
        self.is_running = False
        self.worker_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # 统计信息
        self.stats = {
            "total_logs": 0,
            "dropped_logs": 0,
            "batch_count": 0,
            "queue_full_count": 0
        }
    
    def add_handler(self, handler: logging.Handler) -> None:
        """
        添加处理器
        
        Args:
            handler: 日志处理器
        """
        if handler not in self.handlers:
            self.handlers.append(handler)
    
    def remove_handler(self, handler: logging.Handler) -> None:
        """
        移除处理器
        
        Args:
            handler: 日志处理器
        """
        if handler in self.handlers:
            self.handlers.remove(handler)
    
    def set_level(self, level: Union[int, str]) -> None:
        """
        设置日志级别
        
        Args:
            level: 日志级别
        """
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        self.level = level
    
    async def start(self) -> None:
        """启动异步日志处理"""
        if self.is_running:
            return
        
        self.is_running = True
        self.worker_task = asyncio.create_task(self._worker())
    
    async def stop(self) -> None:
        """停止异步日志处理"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 发送停止信号
        try:
            await self.log_queue.put(None)
        except asyncio.QueueFull:
            pass
        
        # 等待工作任务完成
        if self.worker_task:
            await self.worker_task
            self.worker_task = None
        
        # 处理队列中剩余的日志
        await self._flush_remaining_logs()
    
    async def _worker(self) -> None:
        """异步工作器，处理日志队列"""
        batch: List[LogRecord] = []
        last_batch_time = time.time()
        
        while self.is_running:
            try:
                # 等待日志记录或超时
                timeout = self.batch_timeout - (time.time() - last_batch_time)
                timeout = max(0.1, timeout)  # 最小等待时间
                
                try:
                    record = await asyncio.wait_for(
                        self.log_queue.get(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    record = None
                
                current_time = time.time()
                
                # 检查是否需要处理批次
                should_process_batch = (
                    record is None or  # 超时或停止信号
                    len(batch) >= self.batch_size or  # 达到批次大小
                    (batch and current_time - last_batch_time >= self.batch_timeout)  # 超时
                )
                
                if record is not None:
                    batch.append(record)
                
                # 处理批次
                if should_process_batch and batch:
                    await self._process_batch(batch)
                    batch.clear()
                    last_batch_time = current_time
                    self.stats["batch_count"] += 1
                
                # 检查停止信号
                if record is None and not self.is_running:
                    break
                    
            except Exception as e:
                # 记录工作器错误，但继续运行
                print(f"AsyncLogger worker error: {e}")
        
        # 处理剩余的批次
        if batch:
            await self._process_batch(batch)
    
    async def _process_batch(self, batch: List[LogRecord]) -> None:
        """
        处理日志批次
        
        Args:
            batch: 日志记录批次
        """
        if not batch:
            return
        
        # 为每个处理器处理批次
        tasks = []
        for handler in self.handlers:
            if hasattr(handler, 'emit_async'):
                # 异步处理器
                for record in batch:
                    logging_record = record.to_logging_record()
                    if logging_record.levelno >= handler.level:
                        tasks.append(handler.emit_async(logging_record))
            else:
                # 同步处理器，在线程池中执行
                for record in batch:
                    logging_record = record.to_logging_record()
                    if logging_record.levelno >= handler.level:
                        tasks.append(self._emit_sync_handler(handler, logging_record))
        
        # 并发执行所有处理任务
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _emit_sync_handler(
        self,
        handler: logging.Handler,
        record: logging.LogRecord
    ) -> None:
        """
        在线程池中执行同步处理器
        
        Args:
            handler: 处理器
            record: 日志记录
        """
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, handler.emit, record)
        except Exception as e:
            print(f"Handler error: {e}")
    
    async def _flush_remaining_logs(self) -> None:
        """刷新队列中剩余的日志"""
        remaining_logs = []
        
        while not self.log_queue.empty():
            try:
                record = self.log_queue.get_nowait()
                if record is not None:
                    remaining_logs.append(record)
            except asyncio.QueueEmpty:
                break
        
        if remaining_logs:
            await self._process_batch(remaining_logs)
    
    async def _log(
        self,
        level: int,
        message: str,
        **extra_data: Any
    ) -> bool:
        """
        记录日志
        
        Args:
            level: 日志级别
            message: 日志消息
            **extra_data: 额外数据
            
        Returns:
            是否成功加入队列
        """
        if level < self.level:
            return True
        
        record = LogRecord(
            level=level,
            message=message,
            logger_name=self.name,
            timestamp=time.time(),
            extra_data=extra_data
        )
        
        try:
            self.log_queue.put_nowait(record)
            self.stats["total_logs"] += 1
            return True
        except asyncio.QueueFull:
            self.stats["dropped_logs"] += 1
            self.stats["queue_full_count"] += 1
            return False
    
    async def debug(self, message: str, **extra_data: Any) -> bool:
        """记录DEBUG级别日志"""
        return await self._log(logging.DEBUG, message, **extra_data)
    
    async def info(self, message: str, **extra_data: Any) -> bool:
        """记录INFO级别日志"""
        return await self._log(logging.INFO, message, **extra_data)
    
    async def warning(self, message: str, **extra_data: Any) -> bool:
        """记录WARNING级别日志"""
        return await self._log(logging.WARNING, message, **extra_data)
    
    async def error(self, message: str, **extra_data: Any) -> bool:
        """记录ERROR级别日志"""
        return await self._log(logging.ERROR, message, **extra_data)
    
    async def critical(self, message: str, **extra_data: Any) -> bool:
        """记录CRITICAL级别日志"""
        return await self._log(logging.CRITICAL, message, **extra_data)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "queue_size": self.log_queue.qsize(),
            "is_running": self.is_running,
            "handlers_count": len(self.handlers)
        }


class AsyncLoggerManager:
    """异步日志器管理器"""
    
    def __init__(self):
        """初始化日志器管理器"""
        self.loggers: Dict[str, AsyncLogger] = {}
        self._lock = asyncio.Lock()
    
    async def get_logger(
        self,
        name: str,
        level: int = logging.INFO,
        **kwargs
    ) -> AsyncLogger:
        """
        获取日志器实例
        
        Args:
            name: 日志器名称
            level: 日志级别
            **kwargs: 其他参数
            
        Returns:
            日志器实例
        """
        async with self._lock:
            if name not in self.loggers:
                logger = AsyncLogger(name, level, **kwargs)
                await logger.start()
                self.loggers[name] = logger
            
            return self.loggers[name]
    
    async def configure_logger(
        self,
        name: str,
        config: Dict[str, Any]
    ) -> AsyncLogger:
        """
        配置日志器
        
        Args:
            name: 日志器名称
            config: 配置信息
            
        Returns:
            配置后的日志器
        """
        level = getattr(logging, config.get("level", "INFO").upper())
        
        logger = await self.get_logger(
            name,
            level=level,
            queue_size=config.get("queue_size", 10000),
            batch_size=config.get("batch_size", 100),
            batch_timeout=config.get("batch_timeout", 1.0)
        )
        
        # 清除现有处理器
        logger.handlers.clear()
        
        # 添加配置的处理器
        handlers = config.get("handlers", [])
        for handler_config in handlers:
            handler = await self._create_handler(handler_config)
            if handler:
                logger.add_handler(handler)
        
        return logger
    
    async def _create_handler(self, config: Dict[str, Any]) -> Optional[logging.Handler]:
        """
        创建处理器
        
        Args:
            config: 处理器配置
            
        Returns:
            处理器实例
        """
        handler_type = config.get("type")
        
        if handler_type == "file":
            handler = AsyncFileHandler(
                filename=config["filename"],
                encoding=config.get("encoding", "utf-8")
            )
        elif handler_type == "rotating_file":
            handler = AsyncRotatingFileHandler(
                filename=config["filename"],
                max_bytes=config.get("max_bytes", 100 * 1024 * 1024),
                backup_count=config.get("backup_count", 10),
                encoding=config.get("encoding", "utf-8"),
                compress=config.get("compress", True)
            )
        elif handler_type == "timed_rotating_file":
            handler = AsyncTimedRotatingFileHandler(
                filename=config["filename"],
                when=config.get("when", "midnight"),
                interval=config.get("interval", 1),
                backup_count=config.get("backup_count", 3),
                encoding=config.get("encoding", "utf-8"),
                compress=config.get("compress", True)
            )
        elif handler_type == "console":
            handler = AsyncConsoleHandler()
        else:
            return None
        
        # 设置格式器
        formatter_config = config.get("formatter", {})
        formatter_type = formatter_config.get("type", "simple")
        
        if formatter_type == "json":
            formatter = JSONFormatter(
                fields=formatter_config.get("fields"),
                timestamp_format=formatter_config.get("timestamp_format"),
                ensure_ascii=formatter_config.get("ensure_ascii", False)
            )
        else:
            formatter = SimpleFormatter(
                format_string=formatter_config.get("format"),
                include_extra=formatter_config.get("include_extra", True)
            )
        
        handler.setFormatter(formatter)
        handler.setLevel(getattr(logging, config.get("level", "INFO").upper()))
        
        return handler
    
    async def stop_all(self) -> None:
        """停止所有日志器"""
        async with self._lock:
            tasks = []
            for logger in self.loggers.values():
                tasks.append(logger.stop())
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            self.loggers.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有日志器的统计信息"""
        return {
            name: logger.get_stats()
            for name, logger in self.loggers.items()
        }


# 全局日志器管理器实例
_logger_manager = AsyncLoggerManager()