"""
缓冲区管理器
高效的缓冲区管理，支持零拷贝
作者: lx
日期: 2025-06-18
"""
from typing import Optional, List
import asyncio

class BufferManager:
    """环形缓冲区管理器"""
    
    def __init__(self, size: int = 1024 * 1024):  # 默认1MB
        self.size = size
        self.buffer = bytearray(size)
        self.read_pos = 0
        self.write_pos = 0
        self._lock = asyncio.Lock()
        
    async def write(self, data: bytes) -> bool:
        """写入数据到缓冲区"""
        async with self._lock:
            data_len = len(data)
            available = self._get_available_write_space()
            
            if data_len > available:
                return False  # 空间不足
                
            # 计算写入位置
            if self.write_pos + data_len <= self.size:
                # 连续写入
                self.buffer[self.write_pos:self.write_pos + data_len] = data
                self.write_pos += data_len
            else:
                # 分段写入
                first_part = self.size - self.write_pos
                self.buffer[self.write_pos:] = data[:first_part]
                self.buffer[:data_len - first_part] = data[first_part:]
                self.write_pos = data_len - first_part
                
            return True
            
    async def read(self, size: Optional[int] = None) -> Optional[bytes]:
        """从缓冲区读取数据"""
        async with self._lock:
            available = self._get_available_read_space()
            if available == 0:
                return None
                
            read_size = min(size, available) if size else available
            
            # 读取数据
            if self.read_pos + read_size <= self.size:
                # 连续读取
                data = bytes(self.buffer[self.read_pos:self.read_pos + read_size])
                self.read_pos += read_size
            else:
                # 分段读取
                first_part = self.size - self.read_pos
                data = bytes(self.buffer[self.read_pos:]) + bytes(self.buffer[:read_size - first_part])
                self.read_pos = read_size - first_part
                
            # 重置位置
            if self.read_pos == self.write_pos:
                self.read_pos = 0
                self.write_pos = 0
                
            return data
            
    def _get_available_write_space(self) -> int:
        """获取可写入空间大小"""
        if self.write_pos >= self.read_pos:
            return self.size - self.write_pos + self.read_pos
        else:
            return self.read_pos - self.write_pos
            
    def _get_available_read_space(self) -> int:
        """获取可读取数据大小"""
        if self.write_pos >= self.read_pos:
            return self.write_pos - self.read_pos
        else:
            return self.size - self.read_pos + self.write_pos