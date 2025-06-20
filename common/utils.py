"""
通用工具模块
Common Utils Module

作者: lx
日期: 2025-06-18
描述: 包含雪花算法ID生成器等通用工具
"""
import time
import threading
from typing import Optional


class SnowflakeIdGenerator:
    """
    雪花算法ID生成器
    
    生成64位唯一ID，格式：
    - 1位符号位 (0)
    - 41位时间戳 (毫秒)
    - 10位机器ID (数据中心ID + 工作机器ID)
    - 12位序列号
    """
    
    def __init__(self, datacenter_id: int = 1, worker_id: int = 1):
        """
        初始化雪花算法生成器
        
        Args:
            datacenter_id: 数据中心ID (0-31)
            worker_id: 工作机器ID (0-31)
        """
        # 验证参数范围
        if not (0 <= datacenter_id <= 31):
            raise ValueError("datacenter_id must be between 0 and 31")
        if not (0 <= worker_id <= 31):
            raise ValueError("worker_id must be between 0 and 31")
            
        self.datacenter_id = datacenter_id
        self.worker_id = worker_id
        
        # 时间戳相关
        self.epoch = 1420070400000  # 2015-01-01 00:00:00 GMT
        self.last_timestamp = -1
        
        # 序列号相关
        self.sequence = 0
        self.sequence_mask = 4095  # 12位序列号的最大值
        
        # 位移量
        self.worker_id_shift = 12
        self.datacenter_id_shift = 17
        self.timestamp_shift = 22
        
        # 线程锁
        self._lock = threading.Lock()
    
    def generate_id(self) -> int:
        """
        生成雪花算法ID
        
        Returns:
            64位唯一ID
        """
        with self._lock:
            timestamp = self._current_timestamp()
            
            # 时钟回拨检测
            if timestamp < self.last_timestamp:
                raise RuntimeError(
                    f"Clock moved backwards. Refusing to generate id for "
                    f"{self.last_timestamp - timestamp} milliseconds"
                )
            
            # 同一毫秒内序列号递增
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.sequence_mask
                if self.sequence == 0:
                    # 序列号用完，等待下一毫秒
                    timestamp = self._wait_next_timestamp(self.last_timestamp)
            else:
                self.sequence = 0
            
            self.last_timestamp = timestamp
            
            # 组合各部分生成最终ID
            snowflake_id = (
                ((timestamp - self.epoch) << self.timestamp_shift) |
                (self.datacenter_id << self.datacenter_id_shift) |
                (self.worker_id << self.worker_id_shift) |
                self.sequence
            )
            
            return snowflake_id
    
    def _current_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)
    
    def _wait_next_timestamp(self, last_timestamp: int) -> int:
        """等待下一个毫秒"""
        timestamp = self._current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._current_timestamp()
        return timestamp
    
    def parse_id(self, snowflake_id: int) -> dict:
        """
        解析雪花算法ID
        
        Args:
            snowflake_id: 雪花算法生成的ID
            
        Returns:
            包含时间戳、数据中心ID、工作机器ID、序列号的字典
        """
        timestamp = ((snowflake_id >> self.timestamp_shift) + self.epoch)
        datacenter_id = (snowflake_id >> self.datacenter_id_shift) & 31
        worker_id = (snowflake_id >> self.worker_id_shift) & 31
        sequence = snowflake_id & self.sequence_mask
        
        return {
            'timestamp': timestamp,
            'datetime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp / 1000)),
            'datacenter_id': datacenter_id,
            'worker_id': worker_id,
            'sequence': sequence
        }


# 全局ID生成器实例
_global_id_generator: Optional[SnowflakeIdGenerator] = None


def get_id_generator(datacenter_id: int = 1, worker_id: int = 1) -> SnowflakeIdGenerator:
    """
    获取全局ID生成器实例
    
    Args:
        datacenter_id: 数据中心ID
        worker_id: 工作机器ID
        
    Returns:
        雪花算法ID生成器实例
    """
    global _global_id_generator
    if _global_id_generator is None:
        _global_id_generator = SnowflakeIdGenerator(datacenter_id, worker_id)
    return _global_id_generator


def generate_id() -> int:
    """
    生成雪花算法ID的便捷函数
    
    Returns:
        64位唯一ID
    """
    return get_id_generator().generate_id()


def parse_id(snowflake_id: int) -> dict:
    """
    解析雪花算法ID的便捷函数
    
    Args:
        snowflake_id: 雪花算法生成的ID
        
    Returns:
        包含时间戳、数据中心ID、工作机器ID、序列号的字典
    """
    return get_id_generator().parse_id(snowflake_id)