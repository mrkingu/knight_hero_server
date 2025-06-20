"""
异步日志系统使用示例
Async Logger System Usage Example

作者: lx
日期: 2025-06-18
描述: 演示如何使用异步日志系统
"""

import asyncio
import time
from pathlib import Path

from common.logger import (
    initialize_loggers,
    get_player_logger,
    get_battle_logger,
    get_system_logger,
    get_error_logger,
    log_player_action,
    log_battle_event,
    log_system_event,
    log_error,
    get_logger_stats,
    shutdown_loggers
)


async def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 初始化日志系统（开发环境配置）
    await initialize_loggers("development")
    
    try:
        # 获取各类日志器
        player_logger = await get_player_logger()
        battle_logger = await get_battle_logger()
        system_logger = await get_system_logger()
        error_logger = await get_error_logger()
        
        # 记录各种类型的日志
        await player_logger.info(
            "玩家登录",
            player_id="player_001",
            ip="192.168.1.100",
            device="iPhone",
            version="1.0.0"
        )
        
        await battle_logger.info(
            "战斗开始",
            battle_id="battle_001",
            player_ids=["player_001", "player_002"],
            battle_type="pvp",
            map_id="map_desert_01"
        )
        
        await system_logger.info(
            "服务器启动完成",
            component="main_server",
            startup_time=2.5,
            memory_usage="256MB"
        )
        
        await error_logger.error(
            "数据库连接失败",
            error_type="ConnectionError",
            trace_id="trace_123",
            database="mongodb",
            retry_count=3
        )
        
        print("✅ 基本日志记录完成")
        
    finally:
        await shutdown_loggers()


async def example_convenience_functions():
    """便捷函数使用示例"""
    print("\n=== 便捷函数使用示例 ===")
    
    await initialize_loggers("development")
    
    try:
        # 使用便捷函数记录日志
        await log_player_action(
            "购买道具",
            player_id="player_001",
            item_id="sword_legendary",
            cost=1000,
            currency="gold"
        )
        
        await log_battle_event(
            "玩家阵亡",
            battle_id="battle_001",
            player_id="player_002",
            damage_source="fireball",
            remaining_hp=0
        )
        
        await log_system_event(
            "缓存更新",
            component="redis_cache",
            cache_type="player_data",
            update_count=150,
            duration_ms=25
        )
        
        await log_error(
            "支付验证失败",
            error_type="PaymentValidationError",
            trace_id="pay_trace_456",
            order_id="order_789",
            amount=99.99
        )
        
        print("✅ 便捷函数日志记录完成")
        
    finally:
        await shutdown_loggers()


async def example_high_performance():
    """高性能批量日志示例"""
    print("\n=== 高性能批量日志示例 ===")
    
    await initialize_loggers("development")
    
    try:
        battle_logger = await get_battle_logger()
        
        # 模拟高频率的战斗事件
        start_time = time.time()
        
        tasks = []
        for i in range(1000):
            tasks.append(battle_logger.info(
                f"战斗事件 {i}",
                battle_id="intensive_battle",
                event_type="skill_cast",
                player_id=f"player_{i % 10}",
                skill_id=f"skill_{i % 20}",
                damage=i * 10,
                timestamp=time.time()
            ))
        
        # 并发发送所有日志
        results = await asyncio.gather(*tasks)
        success_count = sum(1 for r in results if r)
        
        # 等待批量处理完成
        await asyncio.sleep(0.5)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"发送 1000 条日志，成功 {success_count} 条")
        print(f"耗时: {duration:.2f} 秒")
        print(f"平均速度: {success_count/duration:.0f} 条/秒")
        
        # 显示统计信息
        stats = get_logger_stats()
        battle_stats = stats.get("battle", {})
        print(f"批次处理次数: {battle_stats.get('batch_count', 0)}")
        print(f"队列大小: {battle_stats.get('queue_size', 0)}")
        
        print("✅ 高性能批量日志完成")
        
    finally:
        await shutdown_loggers()


async def example_error_scenarios():
    """错误场景处理示例"""
    print("\n=== 错误场景处理示例 ===")
    
    await initialize_loggers("development")
    
    try:
        from common.logger.async_logger import AsyncLogger
        
        # 创建一个小队列的日志器来测试队列满的情况
        test_logger = AsyncLogger(
            "overflow_test",
            queue_size=5,  # 非常小的队列
            batch_size=100,  # 大批次以防止自动处理
            batch_timeout=10.0
        )
        
        await test_logger.start()
        
        # 尝试发送超过队列容量的日志
        success_count = 0
        failed_count = 0
        
        for i in range(10):
            result = await test_logger.info(f"测试消息 {i}")
            if result:
                success_count += 1
            else:
                failed_count += 1
        
        print(f"成功发送: {success_count} 条")
        print(f"失败发送: {failed_count} 条")
        
        # 显示统计信息
        stats = test_logger.get_stats()
        print(f"丢失日志: {stats['dropped_logs']} 条")
        print(f"队列满次数: {stats['queue_full_count']} 次")
        
        await test_logger.stop()
        
        print("✅ 错误场景处理完成")
        
    finally:
        await shutdown_loggers()


async def example_custom_logger():
    """自定义日志器示例"""
    print("\n=== 自定义日志器示例 ===")
    
    from common.logger import get_logger
    
    # 获取自定义日志器
    custom_logger = await get_logger("custom_module")
    
    try:
        # 记录模块特定的日志
        await custom_logger.debug("模块初始化开始")
        await custom_logger.info(
            "模块配置加载",
            config_file="custom_module.yaml",
            config_version="1.2.3",
            load_time_ms=45
        )
        await custom_logger.warning(
            "配置项已过时",
            deprecated_key="old_setting",
            recommended_key="new_setting"
        )
        await custom_logger.info("模块初始化完成")
        
        print("✅ 自定义日志器示例完成")
        
    finally:
        await shutdown_loggers()


async def main():
    """主函数 - 运行所有示例"""
    print("🚀 异步日志系统使用示例")
    print("=" * 50)
    
    # 确保日志目录存在
    Path("logs").mkdir(exist_ok=True)
    
    # 运行所有示例
    await example_basic_usage()
    await example_convenience_functions()
    await example_high_performance()
    await example_error_scenarios()
    await example_custom_logger()
    
    print("\n" + "=" * 50)
    print("🎉 所有示例完成！")
    print("\n检查 logs/ 目录查看生成的日志文件。")


if __name__ == "__main__":
    asyncio.run(main())