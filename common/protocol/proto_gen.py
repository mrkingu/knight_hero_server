"""
Protocol自动生成工具
Protocol Auto-generation Tool

作者: lx
日期: 2025-06-18
描述: 扫描Python类定义，自动生成对应的proto文件，自动调用protoc编译，生成Python绑定代码
"""

import ast
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class FieldInfo:
    """字段信息"""
    name: str
    type_name: str
    field_number: int
    is_repeated: bool = False
    is_optional: bool = False
    default_value: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class MessageInfo:
    """消息信息"""
    name: str
    fields: List[FieldInfo] = field(default_factory=list)
    nested_messages: List['MessageInfo'] = field(default_factory=list)
    comment: Optional[str] = None
    package: Optional[str] = None


@dataclass
class ServiceInfo:
    """服务信息"""
    name: str
    methods: List[Dict[str, str]] = field(default_factory=list)
    comment: Optional[str] = None


class TypeMapping:
    """Python类型到Proto类型的映射"""
    
    PYTHON_TO_PROTO = {
        'int': 'int32',
        'float': 'float',
        'bool': 'bool',
        'str': 'string',
        'bytes': 'bytes',
        'bytearray': 'bytes',
        'List[int]': 'repeated int32',
        'List[float]': 'repeated float',
        'List[str]': 'repeated string',
        'List[bool]': 'repeated bool',
        'Optional[int]': 'int32',
        'Optional[float]': 'float',
        'Optional[str]': 'string',
        'Optional[bool]': 'bool',
        'Optional[bytes]': 'bytes',
    }
    
    @classmethod
    def map_type(cls, python_type: str) -> str:
        """
        将Python类型映射为Proto类型
        
        Args:
            python_type: Python类型字符串
            
        Returns:
            str: Proto类型字符串
        """
        # 直接映射
        if python_type in cls.PYTHON_TO_PROTO:
            return cls.PYTHON_TO_PROTO[python_type]
        
        # 处理List类型
        list_match = re.match(r'List\[(.*)\]', python_type)
        if list_match:
            inner_type = list_match.group(1)
            mapped_inner = cls.map_type(inner_type)
            return f'repeated {mapped_inner}'
        
        # 处理Optional类型
        opt_match = re.match(r'Optional\[(.*)\]', python_type)
        if opt_match:
            inner_type = opt_match.group(1)
            return cls.map_type(inner_type)
        
        # 处理Union类型（简单处理，取第一个类型）
        union_match = re.match(r'Union\[(.*)\]', python_type)
        if union_match:
            first_type = union_match.group(1).split(',')[0].strip()
            return cls.map_type(first_type)
        
        # 默认认为是消息类型
        return python_type


class PythonClassParser:
    """Python类解析器"""
    
    def __init__(self):
        """初始化解析器"""
        self.messages: List[MessageInfo] = []
        self.services: List[ServiceInfo] = []
        self.imports: Set[str] = set()
    
    def parse_file(self, file_path: Path) -> None:
        """
        解析Python文件
        
        Args:
            file_path: Python文件路径
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            self._visit_node(tree)
            
        except Exception as e:
            logger.error(f"Failed to parse file {file_path}: {e}")
            raise
    
    def parse_directory(self, dir_path: Path, pattern: str = "*.py") -> None:
        """
        解析目录中的所有Python文件
        
        Args:
            dir_path: 目录路径
            pattern: 文件模式
        """
        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                logger.info(f"Parsing file: {file_path}")
                self.parse_file(file_path)
    
    def _visit_node(self, node: ast.AST) -> None:
        """递归访问AST节点"""
        if isinstance(node, ast.ClassDef):
            self._parse_class(node)
        elif isinstance(node, ast.FunctionDef):
            # 检查是否是服务方法
            if hasattr(node, 'decorator_list'):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == 'grpc_service':
                        self._parse_service_method(node)
        
        for child in ast.iter_child_nodes(node):
            self._visit_node(child)
    
    def _parse_class(self, class_node: ast.ClassDef) -> None:
        """
        解析类定义
        
        Args:
            class_node: 类AST节点
        """
        # 检查是否是消息类（继承自BaseMessage或包含@dataclass装饰器）
        is_message_class = False
        is_dataclass = False
        
        # 检查基类
        for base in class_node.bases:
            if isinstance(base, ast.Name) and 'Message' in base.id:
                is_message_class = True
                break
        
        # 检查装饰器
        for decorator in class_node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == 'dataclass':
                is_dataclass = True
                break
        
        if not (is_message_class or is_dataclass):
            return
        
        message_info = MessageInfo(
            name=class_node.name,
            comment=ast.get_docstring(class_node)
        )
        
        # 解析字段
        field_number = 1
        for node in class_node.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                field_info = self._parse_field(node, field_number)
                if field_info:
                    message_info.fields.append(field_info)
                    field_number += 1
        
        self.messages.append(message_info)
        logger.debug(f"Parsed message class: {message_info.name} with {len(message_info.fields)} fields")
    
    def _parse_field(self, field_node: ast.AnnAssign, field_number: int) -> Optional[FieldInfo]:
        """
        解析字段定义
        
        Args:
            field_node: 字段AST节点
            field_number: 字段编号
            
        Returns:
            Optional[FieldInfo]: 字段信息
        """
        if not isinstance(field_node.target, ast.Name):
            return None
        
        field_name = field_node.target.id
        type_annotation = self._get_type_annotation(field_node.annotation)
        
        # 检查是否是repeated字段
        is_repeated = 'List[' in type_annotation
        is_optional = 'Optional[' in type_annotation or 'Union[' in type_annotation
        
        # 获取默认值
        default_value = None
        if field_node.value:
            default_value = self._get_default_value(field_node.value)
        
        proto_type = TypeMapping.map_type(type_annotation)
        
        return FieldInfo(
            name=field_name,
            type_name=proto_type,
            field_number=field_number,
            is_repeated=is_repeated,
            is_optional=is_optional,
            default_value=default_value
        )
    
    def _get_type_annotation(self, annotation: ast.AST) -> str:
        """
        获取类型注解字符串
        
        Args:
            annotation: 类型注解AST节点
            
        Returns:
            str: 类型字符串
        """
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Subscript):
            # 处理泛型类型如List[int], Optional[str]等
            value = self._get_type_annotation(annotation.value)
            slice_value = self._get_type_annotation(annotation.slice)
            return f"{value}[{slice_value}]"
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Attribute):
            return f"{self._get_type_annotation(annotation.value)}.{annotation.attr}"
        else:
            return "Any"
    
    def _get_default_value(self, value_node: ast.AST) -> Optional[str]:
        """
        获取默认值
        
        Args:
            value_node: 值AST节点
            
        Returns:
            Optional[str]: 默认值字符串
        """
        if isinstance(value_node, ast.Constant):
            if isinstance(value_node.value, str):
                return f'"{value_node.value}"'
            return str(value_node.value)
        elif isinstance(value_node, ast.Name):
            return value_node.id
        return None
    
    def _parse_service_method(self, method_node: ast.FunctionDef) -> None:
        """
        解析服务方法
        
        Args:
            method_node: 方法AST节点
        """
        # 这里可以扩展服务方法解析逻辑
        pass


class ProtoGenerator:
    """Proto文件生成器"""
    
    def __init__(self, package_name: str = "game.protocol"):
        """
        初始化生成器
        
        Args:
            package_name: Proto包名
        """
        self.package_name = package_name
        self.syntax_version = "proto3"
    
    def generate_proto_content(self, messages: List[MessageInfo], 
                             services: List[ServiceInfo] = None) -> str:
        """
        生成proto文件内容
        
        Args:
            messages: 消息信息列表
            services: 服务信息列表
            
        Returns:
            str: proto文件内容
        """
        lines = []
        
        # 文件头
        lines.extend([
            f'// 自动生成的proto文件',
            f'// Auto-generated proto file',
            f'// 生成时间: {self._get_timestamp()}',
            f'',
            f'syntax = "{self.syntax_version}";',
            f'package {self.package_name};',
            f'',
        ])
        
        # 导入
        lines.extend([
            '// 导入其他proto文件',
            '// Import other proto files',
            '',
        ])
        
        # 生成消息定义
        for message in messages:
            lines.extend(self._generate_message(message))
            lines.append('')
        
        # 生成服务定义
        if services:
            for service in services:
                lines.extend(self._generate_service(service))
                lines.append('')
        
        return '\n'.join(lines)
    
    def _generate_message(self, message: MessageInfo) -> List[str]:
        """
        生成消息定义
        
        Args:
            message: 消息信息
            
        Returns:
            List[str]: 消息定义行
        """
        lines = []
        
        # 消息注释
        if message.comment:
            lines.extend([
                f'// {message.comment}',
                f'// Message: {message.name}',
            ])
        else:
            lines.append(f'// Message: {message.name}')
        
        lines.append(f'message {message.name} {{')
        
        # 字段定义
        for field in message.fields:
            field_lines = self._generate_field(field)
            lines.extend([f'  {line}' for line in field_lines])
        
        # 嵌套消息
        for nested in message.nested_messages:
            nested_lines = self._generate_message(nested)
            lines.extend([f'  {line}' for line in nested_lines])
        
        lines.append('}')
        
        return lines
    
    def _generate_field(self, field: FieldInfo) -> List[str]:
        """
        生成字段定义
        
        Args:
            field: 字段信息
            
        Returns:
            List[str]: 字段定义行
        """
        lines = []
        
        # 字段注释
        if field.comment:
            lines.append(f'// {field.comment}')
        
        # 字段定义
        field_def = f'{field.type_name} {field.name} = {field.field_number};'
        
        # 添加默认值（如果有）
        if field.default_value and self.syntax_version == "proto2":
            field_def = field_def.rstrip(';') + f' [default = {field.default_value}];'
        
        lines.append(field_def)
        
        return lines
    
    def _generate_service(self, service: ServiceInfo) -> List[str]:
        """
        生成服务定义
        
        Args:
            service: 服务信息
            
        Returns:
            List[str]: 服务定义行
        """
        lines = []
        
        if service.comment:
            lines.append(f'// {service.comment}')
        
        lines.append(f'service {service.name} {{')
        
        for method in service.methods:
            method_def = f'  rpc {method["name"]}({method["request"]}) returns ({method["response"]});'
            lines.append(method_def)
        
        lines.append('}')
        
        return lines
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        import datetime
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class ProtoCompiler:
    """Proto编译器"""
    
    def __init__(self, protoc_path: str = "protoc"):
        """
        初始化编译器
        
        Args:
            protoc_path: protoc可执行文件路径
        """
        self.protoc_path = protoc_path
    
    def compile_proto(self, proto_file: Path, output_dir: Path, 
                     python_out: bool = True, grpc_out: bool = True) -> bool:
        """
        编译proto文件
        
        Args:
            proto_file: proto文件路径
            output_dir: 输出目录
            python_out: 是否生成Python代码
            grpc_out: 是否生成gRPC代码
            
        Returns:
            bool: 编译是否成功
        """
        try:
            cmd = [
                'python', '-m', 'grpc_tools.protoc',
                f'--proto_path={proto_file.parent}',
            ]
            
            if python_out:
                cmd.append(f'--python_out={output_dir}')
            
            if grpc_out:
                cmd.append(f'--grpc_python_out={output_dir}')
            
            cmd.append(str(proto_file))
            
            logger.info(f"Compiling proto: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Successfully compiled {proto_file}")
                return True
            else:
                logger.error(f"Failed to compile {proto_file}: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error compiling proto file: {e}")
            return False


class AutoProtoGenerator:
    """自动Proto生成器"""
    
    def __init__(self, package_name: str = "game.protocol"):
        """
        初始化自动生成器
        
        Args:
            package_name: Proto包名
        """
        self.parser = PythonClassParser()
        self.generator = ProtoGenerator(package_name)
        self.compiler = ProtoCompiler()
        self.package_name = package_name
    
    def generate_from_directory(self, source_dir: Path, output_dir: Path, 
                              proto_filename: str = "auto_generated.proto") -> bool:
        """
        从目录生成proto文件
        
        Args:
            source_dir: Python源码目录
            output_dir: 输出目录
            proto_filename: proto文件名
            
        Returns:
            bool: 生成是否成功
        """
        try:
            # 解析Python文件
            logger.info(f"Parsing Python files in {source_dir}")
            self.parser.parse_directory(source_dir)
            
            if not self.parser.messages:
                logger.warning("No message classes found")
                return False
            
            # 生成proto内容
            logger.info(f"Generating proto content for {len(self.parser.messages)} messages")
            proto_content = self.generator.generate_proto_content(
                self.parser.messages, 
                self.parser.services
            )
            
            # 写入proto文件
            output_dir.mkdir(parents=True, exist_ok=True)
            proto_file = output_dir / proto_filename
            
            with open(proto_file, 'w', encoding='utf-8') as f:
                f.write(proto_content)
            
            logger.info(f"Generated proto file: {proto_file}")
            
            # 编译proto文件
            logger.info("Compiling proto file")
            success = self.compiler.compile_proto(proto_file, output_dir)
            
            if success:
                logger.info("Auto-generation completed successfully")
            else:
                logger.error("Proto compilation failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Auto-generation failed: {e}")
            return False
    
    def generate_from_classes(self, class_modules: List[str], output_dir: Path,
                            proto_filename: str = "auto_generated.proto") -> bool:
        """
        从指定的类模块生成proto文件
        
        Args:
            class_modules: 类模块名列表
            output_dir: 输出目录
            proto_filename: proto文件名
            
        Returns:
            bool: 生成是否成功
        """
        try:
            messages = []
            
            # 动态导入并解析类
            for module_name in class_modules:
                try:
                    module = __import__(module_name, fromlist=[''])
                    
                    # 查找消息类
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            hasattr(attr, '__annotations__') and
                            'Message' in str(attr.__bases__)):
                            
                            message_info = self._extract_message_info(attr)
                            if message_info:
                                messages.append(message_info)
                                
                except ImportError as e:
                    logger.warning(f"Failed to import module {module_name}: {e}")
                    continue
            
            if not messages:
                logger.warning("No message classes found in specified modules")
                return False
            
            # 生成proto内容
            proto_content = self.generator.generate_proto_content(messages)
            
            # 写入并编译
            output_dir.mkdir(parents=True, exist_ok=True)
            proto_file = output_dir / proto_filename
            
            with open(proto_file, 'w', encoding='utf-8') as f:
                f.write(proto_content)
            
            return self.compiler.compile_proto(proto_file, output_dir)
            
        except Exception as e:
            logger.error(f"Failed to generate from classes: {e}")
            return False
    
    def _extract_message_info(self, cls: type) -> Optional[MessageInfo]:
        """
        从类提取消息信息
        
        Args:
            cls: 类对象
            
        Returns:
            Optional[MessageInfo]: 消息信息
        """
        try:
            message_info = MessageInfo(
                name=cls.__name__,
                comment=cls.__doc__
            )
            
            # 提取字段信息
            field_number = 1
            if hasattr(cls, '__annotations__'):
                for field_name, field_type in cls.__annotations__.items():
                    proto_type = TypeMapping.map_type(str(field_type))
                    
                    field_info = FieldInfo(
                        name=field_name,
                        type_name=proto_type,
                        field_number=field_number
                    )
                    
                    message_info.fields.append(field_info)
                    field_number += 1
            
            return message_info
            
        except Exception as e:
            logger.error(f"Failed to extract message info from {cls}: {e}")
            return None


def main():
    """主函数，用于命令行调用"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Auto-generate proto files from Python classes')
    parser.add_argument('source_dir', help='Source directory containing Python files')
    parser.add_argument('output_dir', help='Output directory for generated proto files')
    parser.add_argument('--package', default='game.protocol', help='Proto package name')
    parser.add_argument('--filename', default='auto_generated.proto', help='Proto filename')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 创建生成器并执行
    generator = AutoProtoGenerator(args.package)
    
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    
    if not source_dir.exists():
        logger.error(f"Source directory does not exist: {source_dir}")
        return 1
    
    success = generator.generate_from_directory(source_dir, output_dir, args.filename)
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())