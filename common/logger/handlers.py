"""
异步日志处理器
Async Log Handlers

作者: lx
日期: 2025-06-18
描述: 提供异步文件写入、文件轮转和自动清理功能
"""

import asyncio
import gzip
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, TextIO, Union

import aiofiles


class AsyncFileHandler(logging.Handler):
    """异步文件处理器基类"""
    
    def __init__(
        self,
        filename: Union[str, Path],
        mode: str = 'a',
        encoding: str = 'utf-8',
        delay: bool = False
    ):
        """
        初始化异步文件处理器
        
        Args:
            filename: 日志文件路径
            mode: 文件打开模式
            encoding: 文件编码
            delay: 是否延迟打开文件
        """
        super().__init__()
        self.filename = Path(filename)
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        self.stream: Optional[TextIO] = None
        self._lock = asyncio.Lock()
        
        # 确保目录存在
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        
        if not delay:
            asyncio.create_task(self._open_file())
    
    async def _open_file(self) -> None:
        """异步打开文件"""
        if self.stream is None:
            try:
                self.stream = await aiofiles.open(
                    self.filename,
                    mode=self.mode,
                    encoding=self.encoding
                )
            except Exception as e:
                print(f"Error opening file {self.filename}: {e}")
                raise
    
    async def _close_file(self) -> None:
        """异步关闭文件"""
        if self.stream:
            await self.stream.close()
            self.stream = None
    
    async def emit_async(self, record: logging.LogRecord) -> None:
        """
        异步写入日志记录
        
        Args:
            record: 日志记录对象
        """
        async with self._lock:
            try:
                if self.stream is None:
                    await self._open_file()
                
                msg = self.format(record)
                await self.stream.write(msg + '\n')
                await self.stream.flush()
                
            except Exception as e:
                self.handleError(record)
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        同步接口，创建异步任务
        
        Args:
            record: 日志记录对象
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit_async(record))
        except RuntimeError:
            # 如果没有运行的事件循环，创建新的
            asyncio.create_task(self.emit_async(record))
    
    async def close_async(self) -> None:
        """异步关闭处理器"""
        await self._close_file()
    
    def close(self) -> None:
        """关闭处理器"""
        if self.stream:
            asyncio.create_task(self.close_async())
        super().close()


class AsyncRotatingFileHandler(AsyncFileHandler):
    """按大小轮转的异步文件处理器"""
    
    def __init__(
        self,
        filename: Union[str, Path],
        mode: str = 'a',
        max_bytes: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 10,
        encoding: str = 'utf-8',
        delay: bool = False,
        compress: bool = True
    ):
        """
        初始化按大小轮转的文件处理器
        
        Args:
            filename: 日志文件路径
            mode: 文件打开模式
            max_bytes: 最大文件大小（字节）
            backup_count: 备份文件数量
            encoding: 文件编码
            delay: 是否延迟打开文件
            compress: 是否压缩旧文件
        """
        super().__init__(filename, mode, encoding, delay)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.compress = compress
    
    async def should_rollover(self, record: logging.LogRecord) -> bool:
        """
        检查是否需要轮转文件
        
        Args:
            record: 日志记录对象
            
        Returns:
            是否需要轮转
        """
        if self.max_bytes <= 0:
            return False
        
        if self.stream is None:
            await self._open_file()
        
        # 检查文件大小
        try:
            current_size = self.filename.stat().st_size
            msg = self.format(record)
            return current_size + len(msg.encode(self.encoding)) >= self.max_bytes
        except (OSError, AttributeError):
            return False
    
    async def do_rollover(self) -> None:
        """执行文件轮转"""
        if self.stream:
            await self.stream.close()
            self.stream = None
        
        # 轮转文件
        for i in range(self.backup_count - 1, 0, -1):
            old_name = f"{self.filename}.{i}"
            new_name = f"{self.filename}.{i + 1}"
            
            if os.path.exists(old_name):
                if os.path.exists(new_name):
                    os.remove(new_name)
                os.rename(old_name, new_name)
        
        # 移动当前文件
        if self.filename.exists():
            backup_name = f"{self.filename}.1"
            if os.path.exists(backup_name):
                os.remove(backup_name)
            os.rename(str(self.filename), backup_name)
            
            # 压缩备份文件
            if self.compress:
                await self._compress_file(backup_name)
        
        # 重新打开文件
        await self._open_file()
    
    async def _compress_file(self, filename: str) -> None:
        """
        压缩文件
        
        Args:
            filename: 要压缩的文件名
        """
        try:
            compressed_name = f"{filename}.gz"
            
            # 使用同步方式压缩以避免复杂的异步问题
            with open(filename, 'rb') as f_in:
                with gzip.open(compressed_name, 'wb') as f_out:
                    f_out.write(f_in.read())
            
            # 删除原文件
            os.remove(filename)
        except Exception as e:
            # 压缩失败时记录错误但不影响日志记录
            print(f"文件压缩失败: {filename}, 错误: {e}")

    
    async def emit_async(self, record: logging.LogRecord) -> None:
        """
        异步写入日志记录（包含轮转检查）
        
        Args:
            record: 日志记录对象
        """
        async with self._lock:
            try:
                if await self.should_rollover(record):
                    await self.do_rollover()
                
                await super().emit_async(record)
                
            except Exception as e:
                self.handleError(record)


class AsyncTimedRotatingFileHandler(AsyncFileHandler):
    """按时间轮转的异步文件处理器"""
    
    def __init__(
        self,
        filename: Union[str, Path],
        when: str = 'midnight',
        interval: int = 1,
        backup_count: int = 3,
        encoding: str = 'utf-8',
        delay: bool = False,
        utc: bool = False,
        compress: bool = True
    ):
        """
        初始化按时间轮转的文件处理器
        
        Args:
            filename: 日志文件路径
            when: 轮转时机 ('S', 'M', 'H', 'D', 'midnight')
            interval: 轮转间隔
            backup_count: 备份文件数量
            encoding: 文件编码
            delay: 是否延迟打开文件
            utc: 是否使用UTC时间
            compress: 是否压缩旧文件
        """
        super().__init__(filename, 'a', encoding, delay)
        self.when = when.upper()
        self.interval = interval
        self.backup_count = backup_count
        self.utc = utc
        self.compress = compress
        
        # 计算轮转时间
        self.suffix = self._get_suffix()
        self.rollover_at = self._compute_rollover()
    
    def _get_suffix(self) -> str:
        """获取文件名后缀格式"""
        if self.when == 'S':
            return "%Y-%m-%d_%H-%M-%S"
        elif self.when == 'M':
            return "%Y-%m-%d_%H-%M"
        elif self.when == 'H':
            return "%Y-%m-%d_%H"
        elif self.when in ('D', 'MIDNIGHT'):
            return "%Y-%m-%d"
        else:
            return "%Y-%m-%d_%H-%M-%S"
    
    def _compute_rollover(self) -> float:
        """计算下次轮转时间"""
        current_time = time.time()
        if self.utc:
            t = time.gmtime(current_time)
        else:
            t = time.localtime(current_time)
        
        if self.when == 'MIDNIGHT' or self.when == 'D':
            # 计算到下个午夜的时间
            future = list(t[:3]) + [0, 0, 0, 0, 0, 0]
            future[2] += self.interval
            return time.mktime(tuple(future))
        elif self.when == 'H':
            return current_time + (self.interval * 3600)
        elif self.when == 'M':
            return current_time + (self.interval * 60)
        elif self.when == 'S':
            return current_time + self.interval
        else:
            return current_time + (self.interval * 86400)  # 默认按天
    
    async def should_rollover(self, record: logging.LogRecord) -> bool:
        """
        检查是否需要轮转文件
        
        Args:
            record: 日志记录对象
            
        Returns:
            是否需要轮转
        """
        return time.time() >= self.rollover_at
    
    async def do_rollover(self) -> None:
        """执行时间轮转"""
        if self.stream:
            await self.stream.close()
            self.stream = None
        
        # 生成备份文件名
        if self.utc:
            time_tuple = time.gmtime()
        else:
            time_tuple = time.localtime()
        
        backup_suffix = time.strftime(self.suffix, time_tuple)
        backup_name = f"{self.filename}.{backup_suffix}"
        
        # 移动当前文件
        if self.filename.exists():
            if os.path.exists(backup_name):
                os.remove(backup_name)
            os.rename(str(self.filename), backup_name)
            
            # 压缩备份文件
            if self.compress:
                await self._compress_file(backup_name)
        
        # 清理过期文件
        await self._cleanup_old_files()
        
        # 重新计算轮转时间
        self.rollover_at = self._compute_rollover()
        
        # 重新打开文件
        await self._open_file()
    
    async def _compress_file(self, filename: str) -> None:
        """压缩文件"""
        try:
            compressed_name = f"{filename}.gz"
            
            # 使用同步方式压缩以避免复杂的异步问题
            with open(filename, 'rb') as f_in:
                with gzip.open(compressed_name, 'wb') as f_out:
                    f_out.write(f_in.read())
            
            os.remove(filename)
        except Exception as e:
            print(f"文件压缩失败: {filename}, 错误: {e}")

    
    async def _cleanup_old_files(self) -> None:
        """清理过期的日志文件"""
        if self.backup_count <= 0:
            return
        
        try:
            # 获取所有相关的日志文件
            log_files = []
            directory = self.filename.parent
            base_name = self.filename.name
            
            for file_path in directory.glob(f"{base_name}.*"):
                if file_path.is_file():
                    # 获取文件修改时间
                    stat = file_path.stat()
                    log_files.append((stat.st_mtime, file_path))
            
            # 按时间排序，删除最旧的文件
            log_files.sort(reverse=True)  # 最新的在前
            
            for _, file_path in log_files[self.backup_count:]:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                    
        except Exception as e:
            print(f"清理日志文件失败: {e}")
    
    async def emit_async(self, record: logging.LogRecord) -> None:
        """
        异步写入日志记录（包含时间轮转检查）
        
        Args:
            record: 日志记录对象
        """
        async with self._lock:
            try:
                if await self.should_rollover(record):
                    await self.do_rollover()
                
                await super().emit_async(record)
                
            except Exception as e:
                self.handleError(record)


class AsyncConsoleHandler(logging.StreamHandler):
    """异步控制台处理器"""
    
    def __init__(self, stream=None):
        """初始化异步控制台处理器"""
        super().__init__(stream)
        self._lock = asyncio.Lock()
    
    async def emit_async(self, record: logging.LogRecord) -> None:
        """
        异步输出到控制台
        
        Args:
            record: 日志记录对象
        """
        async with self._lock:
            try:
                msg = self.format(record)
                stream = self.stream
                stream.write(msg + self.terminator)
                stream.flush()
            except Exception:
                self.handleError(record)
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        同步接口，创建异步任务
        
        Args:
            record: 日志记录对象
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit_async(record))
        except RuntimeError:
            # 如果没有运行的事件循环，使用同步输出
            super().emit(record)