"""
压缩工具
作者: lx
日期: 2025-06-18
"""
import zlib
from typing import Optional

def compress_data(data: bytes, level: int = 6) -> bytes:
    """压缩数据"""
    return zlib.compress(data, level)

def decompress_data(data: bytes) -> bytes:
    """解压缩数据"""
    return zlib.decompress(data)

def should_compress(data: bytes, threshold: int = 128) -> bool:
    """判断是否应该压缩"""
    return len(data) > threshold

def compress_if_beneficial(data: bytes, threshold: int = 128) -> tuple[bytes, bool]:
    """如果有益则压缩数据"""
    if should_compress(data, threshold):
        compressed = compress_data(data)
        # 只有压缩率超过10%才使用压缩版本
        if len(compressed) < len(data) * 0.9:
            return compressed, True
    return data, False

def lz4_compress(data: bytes) -> Optional[bytes]:
    """LZ4压缩"""
    try:
        import lz4.frame
        return lz4.frame.compress(data)
    except ImportError:
        return None

def lz4_decompress(data: bytes) -> Optional[bytes]:
    """LZ4解压缩"""
    try:
        import lz4.frame
        return lz4.frame.decompress(data)
    except ImportError:
        return None