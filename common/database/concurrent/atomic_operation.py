"""
原子操作实现
使用Lua脚本保证操作原子性
作者: lx
日期: 2025-06-20
"""
from typing import Any, Dict, Optional
from .operation_type import OperationType

class AtomicOperation:
    """原子操作封装"""
    
    def __init__(
        self,
        field: str,
        operation: OperationType,
        value: Any,
        min_value: Optional[Any] = None,
        max_value: Optional[Any] = None
    ):
        """
        初始化原子操作
        
        Args:
            field: 字段名
            operation: 操作类型
            value: 操作值
            min_value: 最小值限制
            max_value: 最大值限制
        """
        self.field = field
        self.operation = operation
        self.value = value
        self.min_value = min_value
        self.max_value = max_value
        self.timestamp = None  # 操作时间戳
        self.source = None     # 操作来源
        self.reason = None     # 操作原因
        
    def to_lua_command(self) -> str:
        """转换为Lua命令"""
        if self.operation == OperationType.INCREMENT:
            return self._generate_increment_lua()
        elif self.operation == OperationType.DECREMENT:
            return self._generate_decrement_lua()
        else:
            return self._generate_basic_lua()
            
    def _generate_increment_lua(self) -> str:
        """生成增加操作的Lua代码"""
        lua = f"""
        local current = tonumber(redis.call('HGET', KEYS[1], '{self.field}') or 0)
        local new_value = current + {self.value}
        """
        
        if self.max_value is not None:
            lua += f"""
        if new_value > {self.max_value} then
            new_value = {self.max_value}
        end
        """
        
        if self.min_value is not None:
            lua += f"""
        if new_value < {self.min_value} then
            new_value = {self.min_value}
        end
        """
        
        lua += f"""
        redis.call('HSET', KEYS[1], '{self.field}', new_value)
        return {{current, new_value}}
        """
        
        return lua
        
    def _generate_decrement_lua(self) -> str:
        """生成减少操作的Lua代码"""
        lua = f"""
        local current = tonumber(redis.call('HGET', KEYS[1], '{self.field}') or 0)
        local new_value = current - {self.value}
        """
        
        if self.min_value is not None:
            lua += f"""
        if new_value < {self.min_value} then
            new_value = {self.min_value}
        end
        """
        
        if self.max_value is not None:
            lua += f"""
        if new_value > {self.max_value} then
            new_value = {self.max_value}
        end
        """
        
        lua += f"""
        redis.call('HSET', KEYS[1], '{self.field}', new_value)
        return {{current, new_value}}
        """
        
        return lua
        
    def _generate_basic_lua(self) -> str:
        """生成基础操作的Lua代码"""
        if self.operation == OperationType.SET:
            return f"""
            local current = redis.call('HGET', KEYS[1], '{self.field}')
            redis.call('HSET', KEYS[1], '{self.field}', '{self.value}')
            return {{current, '{self.value}'}}
            """
        return ""