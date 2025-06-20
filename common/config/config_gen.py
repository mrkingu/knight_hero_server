"""
配置类生成器模块
Configuration Class Generator Module

作者: lx
日期: 2025-06-18
描述: 扫描JSON目录并自动生成Python配置类，使用Pydantic模型和类型注解
"""

import os
import json
import ast
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Union
from datetime import datetime
import logging

# 设置日志
logger = logging.getLogger(__name__)


class ConfigClassGenerator:
    """配置类生成器"""
    
    def __init__(self, json_dir: str = "json", output_dir: str = "common/config/generated"):
        """初始化生成器
        
        Args:
            json_dir: JSON配置文件目录
            output_dir: 生成的Python文件输出目录
        """
        self.json_dir = Path(json_dir)
        self.output_dir = Path(output_dir)
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Python类型映射
        self.type_mapping = {
            int: "int",
            float: "float", 
            str: "str",
            bool: "bool",
            list: "List[Any]",
            dict: "Dict[str, Any]"
        }
        
        # 特殊字段的类型推断
        self.field_type_hints = {
            'id': 'int',
            'level': 'int',
            'price': 'int',
            'quality': 'int',
            'damage': 'int',
            'hp': 'int',
            'mp': 'int',
            'attack': 'int',
            'defense': 'int',
            'speed': 'float',
            'rate': 'float',
            'cooldown': 'float',
            'name': 'str',
            'description': 'str',
            'type': 'int',
            'enabled': 'bool',
            'visible': 'bool'
        }
        
    def scan_json_files(self) -> List[Path]:
        """扫描JSON配置文件
        
        Returns:
            JSON文件路径列表
        """
        json_files = list(self.json_dir.glob('*.json'))
        # 排除服务器配置文件
        json_files = [f for f in json_files if f.stem != 'server_config']
        return sorted(json_files)
        
    def analyze_json_structure(self, json_file: Path) -> Dict[str, Any]:
        """分析JSON文件结构
        
        Args:
            json_file: JSON文件路径
            
        Returns:
            结构分析结果
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, dict):
                logger.warning(f"JSON文件 {json_file} 不是字典格式")
                return {}
                
            # 分析字段类型
            field_types = {}
            sample_record = None
            
            # 获取一个示例记录来分析字段
            for key, value in data.items():
                if isinstance(value, dict):
                    sample_record = value
                    break
                    
            if not sample_record:
                logger.warning(f"JSON文件 {json_file} 中没有找到有效记录")
                return {}
                
            # 分析每个字段的类型
            for field_name, field_value in sample_record.items():
                field_type = self._infer_field_type(field_name, field_value, data)
                field_types[field_name] = field_type
                
            return {
                'file_name': json_file.stem,
                'record_count': len(data),
                'field_types': field_types,
                'sample_record': sample_record
            }
            
        except Exception as e:
            logger.error(f"分析JSON文件 {json_file} 失败: {e}")
            return {}
            
    def _infer_field_type(self, field_name: str, field_value: Any, all_data: Dict[str, Any]) -> str:
        """推断字段类型
        
        Args:
            field_name: 字段名称
            field_value: 字段值
            all_data: 所有数据，用于类型一致性检查
            
        Returns:
            推断的Python类型字符串
        """
        # 检查特殊字段的类型提示
        for hint_pattern, hint_type in self.field_type_hints.items():
            if hint_pattern in field_name.lower():
                return hint_type
                
        # 根据值类型推断
        if field_value is None:
            # 检查其他记录中该字段的类型
            for record in all_data.values():
                if isinstance(record, dict) and field_name in record and record[field_name] is not None:
                    return self._get_python_type(type(record[field_name]))
            return "Optional[Any]"
            
        return self._get_python_type(type(field_value))
        
    def _get_python_type(self, python_type: type) -> str:
        """获取Python类型的字符串表示
        
        Args:
            python_type: Python类型
            
        Returns:
            类型字符串
        """
        if python_type in self.type_mapping:
            return self.type_mapping[python_type]
        else:
            return "Any"
            
    def generate_config_class(self, structure: Dict[str, Any]) -> str:
        """生成配置类代码
        
        Args:
            structure: JSON结构分析结果
            
        Returns:
            生成的Python类代码
        """
        class_name = self._to_pascal_case(structure['file_name']) + 'Config'
        field_types = structure['field_types']
        
        # 生成类代码
        lines = [
            f'class {class_name}(BaseConfig):',
            f'    """{"".join([word.capitalize() for word in structure["file_name"].split("_")])}配置"""',
            ''
        ]
        
        # 生成字段定义
        for field_name, field_type in field_types.items():
            # 生成字段注释
            field_desc = self._generate_field_description(field_name)
            
            # 判断是否为可选字段
            is_optional = field_type.startswith('Optional')
            
            if is_optional:
                lines.append(f'    {field_name}: {field_type} = Field(default=None, description="{field_desc}")')
            elif field_type == 'List[Any]':
                lines.append(f'    {field_name}: {field_type} = Field(default_factory=list, description="{field_desc}")')
            elif field_type == 'Dict[str, Any]':
                lines.append(f'    {field_name}: {field_type} = Field(default_factory=dict, description="{field_desc}")')
            else:
                lines.append(f'    {field_name}: {field_type} = Field(description="{field_desc}")')
                
        lines.append('')
        return os.linesep.join(lines)
        
    def _to_pascal_case(self, snake_str: str) -> str:
        """将下划线命名转换为帕斯卡命名
        
        Args:
            snake_str: 下划线命名字符串
            
        Returns:
            帕斯卡命名字符串
        """
        components = snake_str.split('_')
        return ''.join(word.capitalize() for word in components)
        
    def _generate_field_description(self, field_name: str) -> str:
        """生成字段描述
        
        Args:
            field_name: 字段名称
            
        Returns:
            字段描述
        """
        descriptions = {
            'id': 'ID',
            'name': '名称',
            'type': '类型',
            'level': '等级',
            'quality': '品质',
            'price': '价格',
            'damage': '伤害',
            'hp': '生命值',
            'mp': '魔法值',
            'attack': '攻击力',
            'defense': '防御力',
            'speed': '速度',
            'description': '描述',
            'max_stack': '最大堆叠',
            'cooldown': '冷却时间',
            'mana_cost': '魔法消耗',
            'level_requirement': '等级需求',
            'drop_items': '掉落道具',
            'ai_type': 'AI类型'
        }
        
        # 匹配字段名
        for key, desc in descriptions.items():
            if key in field_name.lower():
                return desc
                
        # 如果没有匹配，使用字段名本身
        return field_name.replace('_', ' ').title()
        
    def generate_manager_class(self, all_structures: List[Dict[str, Any]]) -> str:
        """生成配置管理器类
        
        Args:
            all_structures: 所有配置结构
            
        Returns:
            管理器类代码
        """
        lines = [
            'class GeneratedConfigManager:',
            '    """自动生成的配置管理器"""',
            '',
            '    def __init__(self):',
            '        """初始化配置管理器"""'
        ]
        
        # 为每个配置类型生成字典
        for structure in all_structures:
            config_name = structure['file_name']
            class_name = self._to_pascal_case(config_name) + 'Config'
            lines.append(f'        self.{config_name}_config: Dict[int, {class_name}] = {{}}')
            
        lines.extend(['', '    # 配置获取方法'])
        
        # 为每个配置类型生成获取方法
        for structure in all_structures:
            config_name = structure['file_name']
            class_name = self._to_pascal_case(config_name) + 'Config'
            
            lines.extend([
                f'    def get_{config_name}(self, config_id: int) -> Optional[{class_name}]:',
                f'        """获取{self._generate_field_description(config_name)}配置"""',
                f'        return self.{config_name}_config.get(config_id)',
                ''
            ])
            
        lines.extend([
            '    def clear_all(self):',
            '        """清空所有配置"""'
        ])
        
        # 为每个配置类型生成清空方法
        for structure in all_structures:
            config_name = structure['file_name']
            lines.append(f'        self.{config_name}_config.clear()')
            
        lines.append('')
        return os.linesep.join(lines)
        
    def generate_config_file(self, structures: List[Dict[str, Any]], output_file: Path) -> bool:
        """生成配置文件
        
        Args:
            structures: 配置结构列表
            output_file: 输出文件路径
            
        Returns:
            生成是否成功
        """
        try:
            # 生成文件头部
            lines = [
                '"""',
                '自动生成的配置类文件',
                'Auto-generated Configuration Classes',
                '',
                '作者: lx (自动生成)',
                f'日期: {datetime.now().strftime("%Y-%m-%d")}',
                '描述: 根据JSON配置文件自动生成的Pydantic配置类',
                '"""',
                '',
                'from pydantic import BaseModel, Field',
                'from typing import Dict, List, Any, Optional, Union',
                'from common.config.base_config import BaseConfig',
                '',
                '# 自动生成的配置类',
                ''
            ]
            
            # 生成各个配置类
            for structure in structures:
                class_code = self.generate_config_class(structure)
                lines.append(class_code)
                
            # 生成管理器类
            manager_code = self.generate_manager_class(structures)
            lines.append(manager_code)
            
            # 生成全局实例
            lines.extend([
                '',
                '# 全局配置管理器实例',
                'generated_config_manager = GeneratedConfigManager()',
                '',
                'def get_generated_config_manager() -> GeneratedConfigManager:',
                '    """获取自动生成的配置管理器实例"""',
                '    return generated_config_manager'
            ])
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(os.linesep.join(lines))
                
            logger.info(f"成功生成配置文件: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"生成配置文件失败: {e}")
            return False
            
    def generate_all_configs(self) -> Dict[str, bool]:
        """生成所有配置类
        
        Returns:
            生成结果字典
        """
        results = {}
        json_files = self.scan_json_files()
        
        if not json_files:
            logger.info("未找到JSON配置文件")
            return results
            
        logger.info(f"找到 {len(json_files)} 个JSON配置文件，开始生成配置类")
        
        # 分析所有JSON文件结构
        all_structures = []
        for json_file in json_files:
            structure = self.analyze_json_structure(json_file)
            if structure:
                all_structures.append(structure)
                
        if not all_structures:
            logger.warning("没有有效的JSON配置文件结构")
            return results
            
        # 生成配置文件
        output_file = self.output_dir / 'auto_generated_configs.py'
        success = self.generate_config_file(all_structures, output_file)
        results['auto_generated_configs.py'] = success
        
        # 生成__init__.py文件
        init_file = self.output_dir / '__init__.py'
        init_success = self._generate_init_file(init_file)
        results['__init__.py'] = init_success
        
        return results
        
    def _generate_init_file(self, init_file: Path) -> bool:
        """生成__init__.py文件
        
        Args:
            init_file: __init__.py文件路径
            
        Returns:
            生成是否成功
        """
        try:
            content = '''"""
自动生成的配置模块
Auto-generated Configuration Module

作者: lx (自动生成)
日期: {date}
"""

from .auto_generated_configs import (
    GeneratedConfigManager,
    generated_config_manager,
    get_generated_config_manager
)

__all__ = [
    'GeneratedConfigManager',
    'generated_config_manager', 
    'get_generated_config_manager'
]
'''.format(date=datetime.now().strftime("%Y-%m-%d"))

            with open(init_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"成功生成__init__.py文件: {init_file}")
            return True
            
        except Exception as e:
            logger.error(f"生成__init__.py文件失败: {e}")
            return False
            
    def get_generation_info(self) -> Dict[str, Any]:
        """获取生成信息
        
        Returns:
            生成信息字典
        """
        json_files = self.scan_json_files()
        output_files = list(self.output_dir.glob('*.py'))
        
        return {
            "json_dir": str(self.json_dir),
            "output_dir": str(self.output_dir),
            "json_files_count": len(json_files),
            "output_files_count": len(output_files),
            "json_files": [f.name for f in json_files],
            "output_files": [f.name for f in output_files],
            "last_generation_time": datetime.now().isoformat()
        }


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建生成器
    generator = ConfigClassGenerator()
    
    # 生成配置类
    results = generator.generate_all_configs()
    
    # 输出结果
    print("生成结果:")
    for filename, success in results.items():
        status = "成功" if success else "失败"
        print(f"  {filename}: {status}")
        
    # 输出生成信息
    info = generator.get_generation_info()
    print(f"\\n生成信息:")
    print(f"  JSON目录: {info['json_dir']}")
    print(f"  输出目录: {info['output_dir']}")
    print(f"  JSON文件数: {info['json_files_count']}")
    print(f"  输出文件数: {info['output_files_count']}")