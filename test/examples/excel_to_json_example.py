#!/usr/bin/env python3
"""
Excel转JSON配置工具使用示例
作者: lx
日期: 2025-06-20
"""
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.config.excel_to_json import ExcelToJsonConverter, create_sample_excel_files

def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建转换器
    converter = ExcelToJsonConverter()
    
    # 创建示例文件
    print("创建示例Excel文件...")
    create_sample_excel_files()
    
    # 执行批量转换
    print("开始批量转换...")
    results = converter.batch_convert()
    
    # 输出结果
    print("\n转换结果:")
    for filename, success in results.items():
        status = "成功" if success else "失败"
        print(f"  {filename}: {status}")
        
    # 输出转换信息
    info = converter.get_conversion_info()
    print(f"\n转换信息:")
    print(f"  Excel目录: {info['excel_dir']}")
    print(f"  JSON目录: {info['json_dir']}")
    print(f"  Excel文件数: {info['excel_files_count']}")
    print(f"  JSON文件数: {info['json_files_count']}")

if __name__ == "__main__":
    main()