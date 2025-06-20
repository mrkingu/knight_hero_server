"""
操作类型定义
定义所有支持的原子操作
作者: lx
日期: 2025-06-20
"""
from enum import Enum

class OperationType(Enum):
    """原子操作类型"""
    
    # 数值操作
    SET = "set"              # 设置值
    INCREMENT = "incr"       # 增加
    DECREMENT = "decr"       # 减少
    
    # 集合操作  
    ADD_TO_SET = "sadd"      # 添加到集合
    REMOVE_FROM_SET = "srem" # 从集合移除
    
    # 列表操作
    APPEND = "rpush"         # 追加到列表
    PREPEND = "lpush"        # 前置到列表
    
    # 哈希操作
    HSET = "hset"           # 设置哈希字段
    HINCRBY = "hincrby"     # 哈希字段增加