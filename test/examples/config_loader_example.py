#!/usr/bin/env python3
"""
配置加载器使用示例
作者: lx
日期: 2025-06-20
"""
import asyncio
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from common.config.config_loader import initialize_configs, get_config, ConfigManager

async def main():
    """主函数"""
    # 初始化配置
    success = await initialize_configs(auto_reload=True)
    
    if success:
        print("配置初始化成功")
        
        # 测试获取配置
        try:
            item_config = get_config("item")
            print(f"道具配置条目数: {len(item_config)}")
            
            # 显示配置管理器状态
            manager = ConfigManager()
            status = manager.get_status()
            print(f"配置管理器状态: {status}")
            
        except Exception as e:
            print(f"配置测试失败: {e}")
    else:
        print("配置初始化失败")

def run_example():
    """运行示例"""
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    # 运行异步主函数
    asyncio.run(main())

if __name__ == "__main__":
    run_example()