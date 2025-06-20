"""
统一验证工具
作者: lx
日期: 2025-06-20
"""
from typing import Any, Dict, List, Optional, Union, Callable
import re

class ValidationError(Exception):
    """验证错误异常"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation error for field '{field}': {message}")

class Validator:
    """统一验证器"""
    
    @staticmethod
    def required(value: Any, field_name: str = "field") -> bool:
        """验证必填字段"""
        if value is None or value == "":
            raise ValidationError(field_name, "This field is required")
        return True
    
    @staticmethod
    def string_length(value: str, min_len: int = 0, max_len: int = None, field_name: str = "field") -> bool:
        """验证字符串长度"""
        if not isinstance(value, str):
            raise ValidationError(field_name, "Value must be a string")
        
        if len(value) < min_len:
            raise ValidationError(field_name, f"Length must be at least {min_len} characters")
        
        if max_len is not None and len(value) > max_len:
            raise ValidationError(field_name, f"Length must not exceed {max_len} characters")
        
        return True
    
    @staticmethod
    def numeric_range(value: Union[int, float], min_val: Union[int, float] = None, max_val: Union[int, float] = None, field_name: str = "field") -> bool:
        """验证数值范围"""
        if not isinstance(value, (int, float)):
            raise ValidationError(field_name, "Value must be a number")
        
        if min_val is not None and value < min_val:
            raise ValidationError(field_name, f"Value must be at least {min_val}")
        
        if max_val is not None and value > max_val:
            raise ValidationError(field_name, f"Value must not exceed {max_val}")
        
        return True
    
    @staticmethod
    def email_format(value: str, field_name: str = "email") -> bool:
        """验证邮箱格式"""
        if not isinstance(value, str):
            raise ValidationError(field_name, "Email must be a string")
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, value):
            raise ValidationError(field_name, "Invalid email format")
        
        return True
    
    @staticmethod
    def pattern_match(value: str, pattern: str, field_name: str = "field") -> bool:
        """验证正则表达式模式"""
        if not isinstance(value, str):
            raise ValidationError(field_name, "Value must be a string")
        
        if not re.match(pattern, value):
            raise ValidationError(field_name, f"Value does not match required pattern: {pattern}")
        
        return True
    
    @staticmethod
    def in_choices(value: Any, choices: List[Any], field_name: str = "field") -> bool:
        """验证值是否在允许的选择中"""
        if value not in choices:
            raise ValidationError(field_name, f"Value must be one of: {choices}")
        
        return True
    
    @staticmethod
    def player_id_format(value: str, field_name: str = "player_id") -> bool:
        """验证玩家ID格式"""
        return Validator.pattern_match(value, r'^player_\d{10,}$', field_name)
    
    @staticmethod
    def game_id_format(value: str, field_name: str = "game_id") -> bool:
        """验证游戏ID格式"""
        return Validator.pattern_match(value, r'^game_\d{10,}$', field_name)

def validate_data(data: Dict[str, Any], rules: Dict[str, List[Callable]]) -> Dict[str, Any]:
    """
    验证数据字典
    
    Args:
        data: 要验证的数据字典
        rules: 验证规则字典，格式为 {field_name: [validator_functions]}
        
    Returns:
        验证后的数据字典
        
    Raises:
        ValidationError: 验证失败时抛出
    """
    errors = []
    
    for field_name, validators in rules.items():
        value = data.get(field_name)
        
        for validator in validators:
            try:
                validator(value, field_name)
            except ValidationError as e:
                errors.append(e)
    
    if errors:
        # 如果有多个验证错误，抛出第一个
        raise errors[0]
    
    return data

def create_validator(**rules) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    创建验证器函数
    
    Args:
        **rules: 验证规则
        
    Returns:
        验证器函数
    """
    def validator(data: Dict[str, Any]) -> Dict[str, Any]:
        return validate_data(data, rules)
    
    return validator

# 常用验证器
def validate_player_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证玩家数据"""
    rules = {
        'player_id': [Validator.required, Validator.player_id_format],
        'nickname': [Validator.required, lambda v, f: Validator.string_length(v, 1, 50, f)],
        'level': [Validator.required, lambda v, f: Validator.numeric_range(v, 1, 1000, f)]
    }
    return validate_data(data, rules)

def validate_game_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """验证游戏数据"""
    rules = {
        'game_id': [Validator.required, Validator.game_id_format],
        'type': [Validator.required, lambda v, f: Validator.in_choices(v, ['pvp', 'pve'], f)]
    }
    return validate_data(data, rules)

__all__ = [
    'ValidationError', 'Validator', 'validate_data', 'create_validator',
    'validate_player_data', 'validate_game_data'
]