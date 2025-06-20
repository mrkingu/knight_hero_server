"""
校验和工具
作者: lx
日期: 2025-06-18
"""
import hashlib
import zlib

def crc32_checksum(data: bytes) -> int:
    """计算CRC32校验和"""
    return zlib.crc32(data) & 0xffffffff

def md5_checksum(data: bytes) -> str:
    """计算MD5校验和"""
    return hashlib.md5(data).hexdigest()

def sha256_checksum(data: bytes) -> str:
    """计算SHA256校验和"""
    return hashlib.sha256(data).hexdigest()

def verify_checksum(data: bytes, checksum: str, algorithm: str = "md5") -> bool:
    """验证校验和"""
    if algorithm == "md5":
        return md5_checksum(data) == checksum
    elif algorithm == "sha256":
        return sha256_checksum(data) == checksum
    elif algorithm == "crc32":
        return str(crc32_checksum(data)) == checksum
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")