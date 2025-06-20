"""
Excel转JSON工具模块
Excel to JSON Converter Module

作者: lx
日期: 2025-06-18
描述: 扫描Excel文件并转换为JSON格式，支持数据验证和批量转换
"""

import os
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import logging

# 设置日志
logger = logging.getLogger(__name__)


class ExcelToJsonConverter:
    """Excel转JSON转换器"""
    
    def __init__(self, excel_dir: str = "excel", json_dir: str = "json"):
        """初始化转换器
        
        Args:
            excel_dir: Excel文件目录
            json_dir: JSON输出目录
        """
        self.excel_dir = Path(excel_dir)
        self.json_dir = Path(json_dir)
        
        # 创建目录
        self.excel_dir.mkdir(exist_ok=True)
        self.json_dir.mkdir(exist_ok=True)
        
        # 支持的数据类型映射
        self.type_mapping = {
            'int': int,
            'float': float,
            'str': str,
            'string': str,
            'bool': bool,
            'boolean': bool,
            'list': list,
            'array': list
        }
        
    def scan_excel_files(self) -> List[Path]:
        """扫描Excel文件
        
        Returns:
            Excel文件路径列表
        """
        excel_files = []
        for pattern in ['*.xlsx', '*.xls']:
            excel_files.extend(self.excel_dir.glob(pattern))
        return sorted(excel_files)
        
    def parse_excel_sheet(self, file_path: Path, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """解析Excel工作表
        
        Args:
            file_path: Excel文件路径
            sheet_name: 工作表名称，为None时使用第一个工作表
            
        Returns:
            解析后的数据字典
        """
        try:
            # 读取Excel文件
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
            else:
                df = pd.read_excel(file_path)
            
            # 检查是否有必要的列
            if df.empty:
                logger.warning(f"Excel文件 {file_path} 的工作表 {sheet_name} 为空")
                return {}
                
            # 获取列信息
            columns = df.columns.tolist()
            
            # 第一行是数据类型，从第二行开始是实际数据
            if len(df) < 2:
                logger.warning(f"Excel文件 {file_path} 数据行数不足")
                return {}
                
            # 获取数据类型信息（第一行）
            type_row = df.iloc[0]
            
            # 从第二行开始获取实际数据
            data_rows = df.iloc[1:]
            
            result = {}
            
            # 处理每一行数据
            for index, row in data_rows.iterrows():
                # 获取主键（通常是第一列）
                primary_key = None
                if len(columns) > 0:
                    primary_key = row[columns[0]]
                    
                if pd.isna(primary_key):
                    continue
                    
                # 转换数据类型
                record = {}
                for col in columns:
                    value = row[col]
                    col_type = type_row[col] if col in type_row else 'str'
                    
                    # 处理空值
                    if pd.isna(value):
                        if col_type in ['list', 'array']:
                            record[col] = []
                        else:
                            record[col] = None
                        continue
                    
                    # 类型转换
                    try:
                        converted_value = self._convert_value(value, col_type)
                        record[col] = converted_value
                    except Exception as e:
                        logger.warning(f"列 {col} 值 {value} 类型转换失败: {e}")
                        record[col] = value
                        
                # 使用主键作为字典键
                key = str(int(primary_key)) if isinstance(primary_key, float) else str(primary_key)
                result[key] = record
                
            return result
            
        except Exception as e:
            logger.error(f"解析Excel文件 {file_path} 失败: {e}")
            return {}
            
    def _convert_value(self, value: Any, target_type: str) -> Any:
        """转换值的数据类型
        
        Args:
            value: 原始值
            target_type: 目标类型
            
        Returns:
            转换后的值
        """
        if target_type.lower() in ['list', 'array']:
            # 处理列表类型，支持逗号分隔
            if isinstance(value, str):
                if value.strip() == '':
                    return []
                # 尝试JSON解析
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
                # 按逗号分割
                return [item.strip() for item in value.split(',') if item.strip()]
            elif isinstance(value, (list, tuple)):
                return list(value)
            else:
                return [value]
                
        elif target_type.lower() in ['bool', 'boolean']:
            if isinstance(value, str):
                return value.lower() in ['true', '1', 'yes', 'on', '是', '真']
            return bool(value)
            
        elif target_type.lower() == 'int':
            if isinstance(value, str):
                value = value.strip()
            return int(float(value))  # 先转float再转int，避免"1.0"这样的字符串报错
            
        elif target_type.lower() == 'float':
            if isinstance(value, str):
                value = value.strip()
            return float(value)
            
        else:  # 默认字符串类型
            return str(value).strip() if isinstance(value, str) else str(value)
            
    def validate_data(self, data: Dict[str, Any], config_type: str) -> List[str]:
        """验证数据完整性
        
        Args:
            data: 要验证的数据
            config_type: 配置类型（item, skill, npc等）
            
        Returns:
            验证错误列表
        """
        errors = []
        
        if not data:
            errors.append("数据为空")
            return errors
            
        # 根据配置类型进行不同的验证
        if config_type == 'item':
            required_fields = ['item_id', 'name', 'type', 'quality', 'price']
        elif config_type == 'skill':
            required_fields = ['skill_id', 'name', 'type', 'level', 'damage']
        elif config_type == 'npc':
            required_fields = ['npc_id', 'name', 'level', 'hp', 'attack']
        else:
            required_fields = []
            
        # 检查必需字段
        for record_id, record in data.items():
            for field in required_fields:
                if field not in record or record[field] is None:
                    errors.append(f"记录 {record_id} 缺少必需字段: {field}")
                    
        return errors
        
    def convert_file(self, excel_file: Path, output_file: Optional[Path] = None) -> bool:
        """转换单个Excel文件
        
        Args:
            excel_file: Excel文件路径
            output_file: 输出JSON文件路径，为None时自动生成
            
        Returns:
            转换是否成功
        """
        try:
            if not excel_file.exists():
                logger.error(f"Excel文件不存在: {excel_file}")
                return False
                
            # 确定输出文件路径
            if output_file is None:
                json_name = excel_file.stem + '.json'
                output_file = self.json_dir / json_name
                
            # 解析Excel文件
            data = self.parse_excel_sheet(excel_file)
            
            if not data:
                logger.warning(f"Excel文件 {excel_file} 解析后数据为空")
                return False
                
            # 数据验证
            config_type = excel_file.stem.lower()
            errors = self.validate_data(data, config_type)
            if errors:
                logger.warning(f"数据验证发现问题: {errors}")
                
            # 写入JSON文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"成功转换: {excel_file} -> {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"转换文件 {excel_file} 失败: {e}")
            return False
            
    def batch_convert(self) -> Dict[str, bool]:
        """批量转换所有Excel文件
        
        Returns:
            转换结果字典，文件名 -> 是否成功
        """
        results = {}
        excel_files = self.scan_excel_files()
        
        if not excel_files:
            logger.info("未找到Excel文件")
            return results
            
        logger.info(f"找到 {len(excel_files)} 个Excel文件，开始批量转换")
        
        for excel_file in excel_files:
            success = self.convert_file(excel_file)
            results[excel_file.name] = success
            
        # 统计结果
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        logger.info(f"批量转换完成: {success_count}/{total_count} 个文件转换成功")
        
        return results
        
    def get_conversion_info(self) -> Dict[str, Any]:
        """获取转换信息
        
        Returns:
            转换信息字典
        """
        excel_files = self.scan_excel_files()
        json_files = list(self.json_dir.glob('*.json'))
        
        return {
            "excel_dir": str(self.excel_dir),
            "json_dir": str(self.json_dir),
            "excel_files_count": len(excel_files),
            "json_files_count": len(json_files),
            "excel_files": [f.name for f in excel_files],
            "json_files": [f.name for f in json_files],
            "last_scan_time": datetime.now().isoformat()
        }


def create_sample_excel_files(excel_dir: str = "excel"):
    """创建示例Excel文件
    
    Args:
        excel_dir: Excel文件目录
    """
    excel_path = Path(excel_dir)
    excel_path.mkdir(exist_ok=True)
    
    # 创建道具配置Excel示例
    item_data = {
        'item_id': [1001, 1002, 1003],
        'name': ['小血瓶', '大血瓶', '魔法药水'],
        'type': [1, 1, 2],
        'quality': [1, 2, 2],
        'price': [100, 200, 150],
        'description': ['恢复100点生命值', '恢复300点生命值', '恢复200点魔法值'],
        'max_stack': [10, 10, 5],
        'level_requirement': [1, 5, 3]
    }
    
    # 创建数据类型行
    type_row = {
        'item_id': 'int',
        'name': 'str',
        'type': 'int',
        'quality': 'int',
        'price': 'int',
        'description': 'str',
        'max_stack': 'int',
        'level_requirement': 'int'
    }
    
    # 创建DataFrame
    df_types = pd.DataFrame([type_row])
    df_data = pd.DataFrame(item_data)
    df_final = pd.concat([df_types, df_data], ignore_index=True)
    
    # 保存到Excel
    item_file = excel_path / 'item.xlsx'
    df_final.to_excel(item_file, index=False, sheet_name='items')
    
    logger.info(f"创建示例Excel文件: {item_file}")


