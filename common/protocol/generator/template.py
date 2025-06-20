"""
Proto模板定义
作者: lx
日期: 2025-06-18
"""
from datetime import datetime

class ProtoTemplate:
    """Proto文件模板"""
    
    @staticmethod
    def get_header(package_name: str = "game.protocol") -> str:
        """获取proto文件头部"""
        return f'''syntax = "proto3";
package {package_name};

import "google/protobuf/any.proto";

// 自动生成的消息定义
// 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

'''

    @staticmethod
    def get_base_request_fields() -> list:
        """获取基础请求字段"""
        return [
            "int32 sequence = 1;",
            "int64 timestamp = 2;", 
            "string player_id = 3;",
            "map<string, string> metadata = 4;"
        ]
        
    @staticmethod
    def get_base_response_fields() -> list:
        """获取基础响应字段"""
        return [
            "int32 code = 1;",
            "string message = 2;",
            "int32 sequence = 3;",
            "int64 timestamp = 4;",
            "google.protobuf.Any data = 5;"
        ]
        
    @staticmethod
    def format_message(name: str, fields: list, comment: str = "") -> str:
        """格式化消息定义"""
        lines = []
        if comment:
            lines.append(f"// {comment}")
        lines.append(f"message {name} {{")
        lines.extend([f"  {field}" for field in fields])
        lines.append("}")
        lines.append("")
        return "\n".join(lines)