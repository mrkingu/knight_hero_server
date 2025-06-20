"""
Protocol utils module
"""
from .checksum import crc32_checksum, md5_checksum, sha256_checksum, verify_checksum
from .compression import compress_data, decompress_data, should_compress, compress_if_beneficial
from .serializer import serialize_msgpack, deserialize_msgpack, auto_serialize, auto_deserialize

__all__ = [
    "crc32_checksum", "md5_checksum", "sha256_checksum", "verify_checksum",
    "compress_data", "decompress_data", "should_compress", "compress_if_beneficial", 
    "serialize_msgpack", "deserialize_msgpack", "auto_serialize", "auto_deserialize"
]