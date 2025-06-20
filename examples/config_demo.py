#!/usr/bin/env python3
"""
配置系统演示脚本
Configuration System Demo Script

作者: lx
日期: 2025-06-18
描述: 演示配置管理系统的完整功能
"""

import asyncio
import logging
from pathlib import Path
from common.config import (
    ExcelToJsonConverter, ConfigClassGenerator, 
    initialize_configs, get_config_manager,
    create_sample_excel_files
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def demo_config_system():
    """演示配置系统功能"""
    
    print("🎮 骑士英雄配置管理系统演示")
    print("=" * 50)
    
    # 1. 创建示例Excel文件
    print("\n📊 步骤1: 创建示例Excel文件")
    create_sample_excel_files('excel')
    excel_files = list(Path('excel').glob('*.xlsx'))
    print(f"创建了 {len(excel_files)} 个Excel文件: {[f.name for f in excel_files]}")
    
    # 2. Excel转JSON
    print("\n🔄 步骤2: Excel转JSON转换")
    converter = ExcelToJsonConverter()
    conversion_results = converter.batch_convert()
    
    success_count = sum(1 for success in conversion_results.values() if success)
    print(f"转换完成: {success_count}/{len(conversion_results)} 个文件转换成功")
    
    for filename, success in conversion_results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {filename}")
    
    # 3. 生成配置类
    print("\n🏗️  步骤3: 自动生成配置类")
    generator = ConfigClassGenerator()
    generation_results = generator.generate_all_configs()
    
    gen_success_count = sum(1 for success in generation_results.values() if success)
    print(f"生成完成: {gen_success_count}/{len(generation_results)} 个文件生成成功")
    
    for filename, success in generation_results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {filename}")
    
    # 4. 加载配置
    print("\n🚀 步骤4: 加载配置到内存")
    load_success = await initialize_configs()
    
    if load_success:
        print("✅ 配置加载成功")
        
        # 获取配置管理器
        manager = get_config_manager()
        
        # 显示配置统计
        stats = manager.get_config_count()
        print(f"📈 配置统计: {stats}")
        
        # 5. 演示配置访问
        print("\n🎯 步骤5: 配置访问演示")
        
        # 道具配置演示
        print("\n🗡️  道具配置:")
        item_1001 = manager.get_item(1001)
        if item_1001:
            print(f"  ID: {item_1001.item_id}")
            print(f"  名称: {item_1001.name}")
            print(f"  类型: {item_1001.type}")
            print(f"  品质: {item_1001.quality}")
            print(f"  价格: {item_1001.price} 金币")
            print(f"  描述: {item_1001.description}")
            print(f"  最大堆叠: {item_1001.max_stack}")
            print(f"  等级需求: {item_1001.level_requirement}")
        
        # 技能配置演示
        print("\n🔥 技能配置:")
        skill_2001 = manager.get_skill(2001)
        if skill_2001:
            print(f"  ID: {skill_2001.skill_id}")
            print(f"  名称: {skill_2001.name}")
            print(f"  类型: {skill_2001.type}")
            print(f"  等级: {skill_2001.level}")
            print(f"  伤害: {skill_2001.damage}")
            print(f"  魔法消耗: {skill_2001.mana_cost}")
            print(f"  冷却时间: {skill_2001.cooldown}秒")
            print(f"  描述: {skill_2001.description}")
        
        # NPC配置演示
        print("\n👹 NPC配置:")
        npc_3001 = manager.get_npc(3001)
        if npc_3001:
            print(f"  ID: {npc_3001.npc_id}")
            print(f"  名称: {npc_3001.name}")
            print(f"  等级: {npc_3001.level}")
            print(f"  生命值: {npc_3001.hp}")
            print(f"  攻击力: {npc_3001.attack}")
            print(f"  防御力: {npc_3001.defense}")
            print(f"  掉落道具: {npc_3001.drop_items}")
            print(f"  AI类型: {npc_3001.ai_type}")
        
        # 6. 演示类型过滤
        print("\n🔍 步骤6: 类型过滤演示")
        
        # 获取类型1的道具
        type_1_items = manager.get_items_by_type(1)
        print(f"\n类型1的道具 ({len(type_1_items)}个):")
        for item in type_1_items:
            print(f"  - {item.name} (ID: {item.item_id}, 价格: {item.price})")
        
        # 获取类型1的技能
        type_1_skills = manager.get_skills_by_type(1)
        print(f"\n类型1的技能 ({len(type_1_skills)}个):")
        for skill in type_1_skills:
            print(f"  - {skill.name} (ID: {skill.skill_id}, 伤害: {skill.damage})")
        
        # 7. 配置验证
        print("\n🔍 步骤7: 配置验证")
        validation_errors = manager.validate_all_configs()
        
        has_errors = any(validation_errors.values())
        if has_errors:
            print("❌ 发现配置验证错误:")
            for config_type, errors in validation_errors.items():
                if errors:
                    print(f"  {config_type}: {errors}")
        else:
            print("✅ 所有配置验证通过")
        
        # 8. 性能测试
        print("\n⚡ 步骤8: 性能测试")
        
        import time
        
        # 测试配置访问性能
        start_time = time.time()
        for _ in range(1000):
            manager.get_item(1001)
            manager.get_skill(2001)
            manager.get_npc(3001)
        end_time = time.time()
        
        access_time = (end_time - start_time) * 1000
        print(f"3000次配置访问耗时: {access_time:.2f}ms")
        print(f"平均每次访问: {access_time/3000:.4f}ms")
        
        # 测试类型过滤性能
        start_time = time.time()
        for _ in range(100):
            manager.get_items_by_type(1)
            manager.get_skills_by_type(1)
        end_time = time.time()
        
        filter_time = (end_time - start_time) * 1000
        print(f"200次类型过滤耗时: {filter_time:.2f}ms")
        print(f"平均每次过滤: {filter_time/200:.4f}ms")
        
    else:
        print("❌ 配置加载失败")
    
    print("\n🎉 配置系统演示完成!")
    print("=" * 50)


def demo_hot_reload():
    """演示热更新功能"""
    print("\n🔄 热更新功能演示")
    print("注意: 这是一个简化的演示，实际使用中需要在异步环境中运行")
    
    from common.config import ConfigLoader
    
    def on_config_reload(file_path):
        print(f"🔄 检测到配置文件变更: {file_path}")
        print("🔄 配置已自动重载")
    
    # 创建带热更新的加载器
    loader = ConfigLoader(auto_reload=True)
    loader.add_reload_callback(on_config_reload)
    
    print("✅ 热更新监控已启用")
    print("💡 提示: 修改json目录下的配置文件将自动触发重载")


def show_file_structure():
    """显示文件结构"""
    print("\n📁 配置系统文件结构:")
    
    structure = {
        "common/config/": [
            "__init__.py",
            "base_config.py",
            "excel_to_json.py", 
            "config_gen.py",
            "config_loader.py",
            "generated/"
        ],
        "excel/": [
            "item.xlsx",
            "skill.xlsx",
            "npc.xlsx"
        ],
        "json/": [
            "item.json",
            "skill.json", 
            "npc.json"
        ]
    }
    
    for directory, files in structure.items():
        print(f"\n📂 {directory}")
        for file in files:
            if file.endswith('/'):
                print(f"  📂 {file}")
            else:
                print(f"  📄 {file}")


async def main():
    """主函数"""
    print("🌟 欢迎使用骑士英雄配置管理系统")
    print("本演示将展示配置系统的完整功能")
    print()
    
    # 显示文件结构
    show_file_structure()
    
    # 主要演示
    await demo_config_system()
    
    # 热更新演示
    demo_hot_reload()
    
    print("\n📚 更多信息请参考:")
    print("  - 文档: doc/CONFIG_SYSTEM.md")
    print("  - 测试: test/test_config.py")
    print("  - 示例: 当前脚本")
    
    print("\n🚀 开始使用配置系统:")
    print("```python")
    print("from common.config import initialize_configs, get_config_manager")
    print("")
    print("# 初始化配置")
    print("await initialize_configs()")
    print("")
    print("# 使用配置")
    print("manager = get_config_manager()")
    print("item = manager.get_item(1001)")
    print("```")


if __name__ == "__main__":
    asyncio.run(main())