"""
Proto生成器 - integration layer for tests
作者: lx
日期: 2025-06-18
"""
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FieldInfo:
    """字段信息"""
    name: str
    type_name: str
    field_number: int

@dataclass 
class MessageInfo:
    """消息信息"""
    name: str
    fields: List[FieldInfo]
    comment: str = ""

class TypeMapping:
    """类型映射"""
    
    @staticmethod
    def map_type(python_type: str) -> str:
        """Python类型转Proto类型"""
        type_mapping = {
            "int": "int32",
            "float": "float", 
            "str": "string",
            "bool": "bool",
            "bytes": "bytes",
            "Dict[str, Any]": "map<string, string>",
            "List[str]": "repeated string",
            "List[int]": "repeated int32",
            "List[bool]": "repeated bool",
            "Optional[str]": "string",
            "Optional[int]": "int32",
            "Optional[bool]": "bool"
        }
        return type_mapping.get(python_type, "string")

class ProtoGenerator:
    """Proto文件生成器"""
    
    def __init__(self, package_name: str):
        self.package_name = package_name
        
    def generate_proto_content(self, messages: List[MessageInfo]) -> str:
        """生成proto文件内容"""
        lines = [
            'syntax = "proto3";',
            f'package {self.package_name};',
            '',
            'import "google/protobuf/any.proto";',
            '',
            f'// 自动生成的消息定义',
            f'// 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '',
        ]
        
        for message in messages:
            if message.comment:
                lines.append(f"// {message.comment}")
            lines.append(f"message {message.name} {{")
            
            for field in message.fields:
                lines.append(f"  {field.type_name} {field.name} = {field.field_number};")
                
            lines.append("}")
            lines.append("")
            
        return "\n".join(lines)

class AutoProtoGenerator:
    """自动Proto生成器"""
    pass

class PythonClassParser:
    """Python类解析器"""
    pass

__all__ = [
    "AutoProtoGenerator",
    "PythonClassParser", 
    "ProtoGenerator",
    "TypeMapping",
    "MessageInfo",
    "FieldInfo"
]