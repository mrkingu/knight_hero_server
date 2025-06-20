"""
数据库层使用示例
Database Layer Usage Examples

作者: lx
日期: 2025-06-18
"""
import asyncio
from common.database import (
    get_redis_cache, get_mongo_client, get_operation_logger, 
    get_repository_manager, PlayerRepository
)


async def example_payment_callback():
    """支付回调示例 - 自动处理并发和幂等性"""
    
    # 获取Repository管理器
    redis_client = await get_redis_cache()
    mongo_client = await get_mongo_client()
    operation_logger = await get_operation_logger(mongo_client)
    repo_manager = await get_repository_manager(redis_client, mongo_client)
    await repo_manager.initialize(operation_logger)
    
    # 获取玩家Repository
    player_repo = repo_manager.get_repository("players")
    
    # 支付回调 - 直接调用即可，Repository层处理并发和幂等性
    order_id = "order_12345"
    player_id = "player_001"
    diamond_amount = 100
    
    result = await player_repo.increment(
        entity_id=player_id,
        field="diamond",
        value=diamond_amount,
        source="payment",
        reason="充值订单",
        metadata={"order_id": order_id}
    )
    
    print(f"支付处理结果: {result}")
    return result


async def example_daily_reward():
    """每日奖励示例 - 自动处理重复发放问题"""
    
    redis_client = await get_redis_cache()
    mongo_client = await get_mongo_client()
    operation_logger = await get_operation_logger(mongo_client)
    repo_manager = await get_repository_manager(redis_client, mongo_client)
    await repo_manager.initialize(operation_logger)
    
    player_repo = repo_manager.get_repository("players")
    
    # 每日奖励 - 自动处理重复发放
    from datetime import datetime
    task_id = f"daily_reward_{datetime.now().strftime('%Y%m%d')}"
    rewards = {"diamond": 50, "gold": 1000}
    
    player_ids = ["player_001", "player_002", "player_003"]
    
    for player_id in player_ids:
        result = await player_repo.batch_modify(
            entity_id=player_id,
            operations=[
                {
                    "field": "diamond",
                    "operation": "incr",
                    "value": 50
                },
                {
                    "field": "gold", 
                    "operation": "incr",
                    "value": 1000
                }
            ],
            source="schedule",
            reason=f"每日奖励_{task_id}"
        )
        print(f"玩家 {player_id} 每日奖励: {result}")


async def example_item_purchase():
    """道具购买示例 - 自动检查余额"""
    
    redis_client = await get_redis_cache()
    mongo_client = await get_mongo_client()
    operation_logger = await get_operation_logger(mongo_client)
    repo_manager = await get_repository_manager(redis_client, mongo_client)
    await repo_manager.initialize(operation_logger)
    
    player_repo = repo_manager.get_repository("players")
    
    player_id = "player_001"
    item_cost = 100  # 道具花费100钻石
    
    # 消耗钻石 - 自动检查余额是否足够
    result = await player_repo.decrement_with_check(
        entity_id=player_id,
        field="diamond",
        value=item_cost,
        source="shop",
        reason="购买道具"
    )
    
    if result.get("success"):
        print("道具购买成功")
        # 可以继续添加道具到背包的逻辑
    else:
        print(f"道具购买失败: {result.get('reason')}")
    
    return result


async def example_concurrent_operations():
    """并发操作示例 - 展示如何处理高并发场景"""
    
    redis_client = await get_redis_cache()
    mongo_client = await get_mongo_client()
    operation_logger = await get_operation_logger(mongo_client)
    repo_manager = await get_repository_manager(redis_client, mongo_client)
    await repo_manager.initialize(operation_logger)
    
    player_repo = repo_manager.get_repository("players")
    
    player_id = "player_001"
    
    # 模拟多个并发操作
    tasks = []
    
    # 同时进行的操作：
    # 1. 支付回调加钻石
    # 2. 活动奖励加金币
    # 3. 游戏消耗体力
    # 4. 任务奖励加经验
    
    tasks.append(player_repo.increment(
        entity_id=player_id,
        field="diamond", 
        value=200,
        source="payment",
        reason="充值"
    ))
    
    tasks.append(player_repo.increment(
        entity_id=player_id,
        field="gold",
        value=5000,
        source="activity", 
        reason="活动奖励"
    ))
    
    tasks.append(player_repo.decrement_with_check(
        entity_id=player_id,
        field="energy",
        value=10,
        source="game",
        reason="关卡消耗"
    ))
    
    tasks.append(player_repo.increment(
        entity_id=player_id,
        field="exp",
        value=100,
        source="task",
        reason="任务完成"
    ))
    
    # 并发执行所有操作
    results = await asyncio.gather(*tasks)
    
    print("并发操作结果:")
    for i, result in enumerate(results):
        print(f"操作 {i+1}: {result}")
    
    return results


async def example_audit_and_rollback():
    """审计和回滚示例"""
    
    redis_client = await get_redis_cache()
    mongo_client = await get_mongo_client()
    operation_logger = await get_operation_logger(mongo_client)
    repo_manager = await get_repository_manager(redis_client, mongo_client)
    await repo_manager.initialize(operation_logger)
    
    player_id = "player_001"
    
    # 查看操作历史
    history = await operation_logger.get_operation_history(
        entity_type="players",
        entity_id=player_id,
        limit=10
    )
    
    print(f"玩家 {player_id} 最近10次操作:")
    for op in history:
        print(f"- {op['timestamp']}: {op['operation_type']} {op['field_name']} "
              f"{op['old_value']} -> {op['new_value']} ({op['reason']})")
    
    # 生成审计报告
    from datetime import datetime, timedelta
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    report = await operation_logger.generate_audit_report(
        start_time=start_time,
        end_time=end_time,
        entity_types=["players"]
    )
    
    print(f"24小时审计报告: {report}")
    
    return history, report


async def main():
    """主函数 - 运行所有示例"""
    print("🚀 数据库层使用示例\n")
    
    try:
        print("1. 支付回调示例")
        await example_payment_callback()
        print("✅ 支付回调完成\n")
        
        print("2. 每日奖励示例") 
        await example_daily_reward()
        print("✅ 每日奖励完成\n")
        
        print("3. 道具购买示例")
        await example_item_purchase() 
        print("✅ 道具购买完成\n")
        
        print("4. 并发操作示例")
        await example_concurrent_operations()
        print("✅ 并发操作完成\n")
        
        print("5. 审计和回滚示例")
        await example_audit_and_rollback()
        print("✅ 审计查询完成\n")
        
        print("🎉 所有示例运行完成！")
        
    except Exception as e:
        print(f"❌ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理资源
        try:
            from common.database import (
                close_redis_cache, close_mongo_client, 
                close_operation_logger, close_repository_manager
            )
            
            await close_repository_manager()
            await close_operation_logger()
            await close_mongo_client()
            await close_redis_cache()
            
            print("🔒 资源清理完成")
        except:
            pass


if __name__ == "__main__":
    """
    运行示例
    注意：需要先启动Redis和MongoDB服务
    """
    print("注意：此示例需要Redis和MongoDB服务，当前为演示模式")
    print("在生产环境中请确保服务已启动并配置正确的连接参数\n")
    
    # asyncio.run(main())