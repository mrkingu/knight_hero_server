"""
Proto文件生成器
扫描所有消息类并生成统一的proto文件
作者: lx
日期: 2025-06-18
"""
import os
import ast
from typing import Dict, List, Set
from pathlib import Path
import subprocess
from datetime import datetime

class ProtoGenerator:
    """Proto文件生成器"""
    
    def __init__(self, message_dir: str, output_file: str = "game_messages.proto"):
        self.message_dir = Path(message_dir)
        self.output_file = output_file
        self.messages: Dict[str, Dict] = {}
        
    def scan_messages(self):
        """扫描所有消息定义"""
        for py_file in self.message_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
                
            self._parse_file(py_file)
            
    def _parse_file(self, file_path: Path):
        """解析Python文件"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        try:
            tree = ast.parse(content)
        except SyntaxError:
            print(f"Parse error in {file_path}")
            return
            
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 检查是否有@message装饰器
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                        if decorator.func.id == "message":
                            self._parse_message_class(node, file_path)
                            
    def _parse_message_class(self, class_node: ast.ClassDef, file_path: Path):
        """解析消息类"""
        message_info = {
            "name": class_node.name,
            "fields": [],
            "file": str(file_path),
            "base_class": None
        }
        
        # 获取基类
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                message_info["base_class"] = base.id
                
        # 解析字段
        for node in class_node.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                field_info = {
                    "name": node.target.id,
                    "type": self._get_type_name(node.annotation),
                    "default": None
                }
                
                if node.value:
                    field_info["default"] = ast.unparse(node.value)
                    
                message_info["fields"].append(field_info)
                
        self.messages[class_node.name] = message_info
        
    def _get_type_name(self, annotation) -> str:
        """获取类型名称"""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            # 处理泛型类型如 Optional[str], List[int]
            return ast.unparse(annotation)
        else:
            return "Any"
            
    def generate_proto(self):
        """生成proto文件"""
        lines = [
            'syntax = "proto3";',
            'package game.protocol;',
            '',
            'import "google/protobuf/any.proto";',
            '',
            '// 自动生成的消息定义',
            f'// 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '',
        ]
        
        # 生成消息定义
        for msg_name, msg_info in sorted(self.messages.items()):
            lines.append(f"// {msg_info['file']}")
            lines.append(f"message {msg_name} {{")
            
            # 添加基类字段
            if msg_info["base_class"] == "BaseRequest":
                lines.extend([
                    "  string sequence = 1;",
                    "  int64 timestamp = 2;",
                    "  string player_id = 3;",
                    "  map<string, string> metadata = 4;",
                ])
                field_num = 5
            elif msg_info["base_class"] == "BaseResponse":
                lines.extend([
                    "  int32 code = 1;",
                    "  string message = 2;",
                    "  string sequence = 3;",
                    "  int64 timestamp = 4;",
                    "  google.protobuf.Any data = 5;",
                ])
                field_num = 6
            else:
                field_num = 1
                
            # 添加自定义字段
            for field in msg_info["fields"]:
                if field["name"] in ["sequence", "timestamp", "player_id", "metadata", 
                                   "code", "message", "data"]:
                    continue
                    
                proto_type = self._python_to_proto_type(field["type"])
                lines.append(f"  {proto_type} {field['name']} = {field_num};")
                field_num += 1
                
            lines.append("}")
            lines.append("")
            
        # 写入文件
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        # 编译proto文件
        self._compile_proto()
        
    def _python_to_proto_type(self, python_type: str) -> str:
        """Python类型转Proto类型"""
        type_mapping = {
            "str": "string",
            "int": "int32",
            "float": "float",
            "bool": "bool",
            "bytes": "bytes",
            "Dict[str, Any]": "map<string, string>",
            "List[str]": "repeated string",
            "List[int]": "repeated int32",
            "Optional[str]": "string",
            "Optional[int]": "int32",
            "Optional[Dict[str, Any]]": "map<string, string>",
        }
        
        return type_mapping.get(python_type, "string")
        
    def _compile_proto(self):
        """编译proto文件"""
        try:
            subprocess.run([
                "protoc",
                f"--python_out=.",
                f"--pyi_out=.",
                self.output_file
            ], check=True)
            print(f"Successfully compiled {self.output_file}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to compile proto: {e}")
        except FileNotFoundError:
            print("protoc not found, skipping proto compilation")