#!/usr/bin/env python3
"""
配置类生成器使用示例
作者: lx
日期: 2025-06-20
"""
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.config.config_gen import ConfigClassGenerator

def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建生成器
    generator = ConfigClassGenerator()
    
    # 生成配置类
    print("开始生成配置类...")
    results = generator.generate_all_configs()
    
    # 输出结果
    print(f"\n生成结果:")
    for config_name, success in results.items():
        status = "成功" if success else "失败"
        print(f"  {config_name}: {status}")

if __name__ == "__main__":
    main()