"""
Logic服务使用示例
Logic Service Usage Example

作者: lx
日期: 2025-06-20
描述: 演示Logic服务的完整使用方法，包括处理器、服务、排行榜、任务管理
"""

import asyncio
import logging
import json
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def demo_handler_system():
    """演示Handler系统"""
    print("\n" + "="*50)
    print("1. Handler系统演示")
    print("="*50)
    
    from services.logic.handlers.base_handler import BaseHandler, handler, get_handler_registry
    from common.protocol.core.message_type import MessageType
    
    # 创建自定义处理器演示
    class DemoHandler(BaseHandler):
        @handler(cmd=9001)
        async def handle_demo(self, req):
            """演示处理器"""
            return {
                "code": 0,
                "message": "演示处理器执行成功",
                "data": {
                    "received_data": getattr(req, 'data', 'no data'),
                    "timestamp": datetime.now().isoformat()
                }
            }
    
    # 获取所有注册的处理器
    registry = get_handler_registry()
    print(f"已注册的处理器:")
    for cmd in sorted(registry.keys()):
        handler_func = registry[cmd]
        print(f"  命令 {cmd}: {handler_func.__name__}")
    
    # 演示处理器调用
    demo_handler = DemoHandler()
    mock_request = type('MockRequest', (), {'data': '测试数据', 'MESSAGE_TYPE': 9001})()
    
    try:
        response = await demo_handler.handle_demo(mock_request)
        print(f"\n处理器响应: {json.dumps(response, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"处理器执行出错: {e}")


async def demo_player_service():
    """演示玩家服务"""
    print("\n" + "="*50)
    print("2. 玩家服务演示")
    print("="*50)
    
    from services.logic.services.player_service import PlayerService
    from unittest.mock import AsyncMock, MagicMock
    
    # 创建模拟的数据库客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    mock_mongo = MagicMock()
    
    # 创建玩家服务
    player_service = PlayerService(mock_redis, mock_mongo)
    
    # 模拟基础方法
    player_service.get_by_id = AsyncMock()
    player_service.create = AsyncMock()
    player_service.update = AsyncMock()
    player_service.increment = AsyncMock(return_value={"success": True})
    
    print("创建新玩家...")
    player = await player_service.get_or_create("demo_player", nickname="演示玩家")
    
    print(f"玩家信息:")
    print(f"  ID: {player.player_id}")
    print(f"  昵称: {player.nickname}")
    print(f"  等级: {player.level}")
    print(f"  金币: {player.gold}")
    print(f"  钻石: {player.diamond}")
    print(f"  体力: {player.energy}")
    print(f"  VIP等级: {player.vip_level}")
    
    # 演示业务方法
    print(f"\n演示业务操作:")
    
    # 模拟获取玩家数据用于经验计算
    player_service.get_by_id.return_value = {
        "level": 1,
        "exp": 50,
        "gold": 1000
    }
    
    exp_result = await player_service.add_experience("demo_player", 200, "quest_reward")
    print(f"添加经验结果: 升级={exp_result.get('level_up')}, 新等级={exp_result.get('new_level')}")


async def demo_ranking_system():
    """演示排行榜系统"""
    print("\n" + "="*50)
    print("3. 排行榜系统演示")
    print("="*50)
    
    from services.logic.ranking.rank_service import RankService, RankType
    from unittest.mock import AsyncMock, MagicMock
    
    # 创建模拟Redis客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    
    # 创建排行榜服务
    rank_service = RankService(mock_redis)
    
    print("排行榜类型:")
    for rank_type in RankType:
        config = rank_service.rank_configs[rank_type]
        print(f"  {rank_type.value}: 最大容量 {config['max_size']}")
    
    # 模拟排行榜数据
    mock_ranking_data = [
        ("player1", 100),
        ("player2", 95),
        ("player3", 90),
        ("player4", 85),
        ("player5", 80)
    ]
    
    mock_redis.client.zrevrange.return_value = mock_ranking_data
    mock_redis.client.get.return_value = None
    
    # 获取等级排行榜
    ranking = await rank_service.get_top_players(RankType.LEVEL, 0, 5, False)
    
    print(f"\n等级排行榜 TOP 5:")
    for entry in ranking:
        print(f"  第{entry['rank']}名: {entry['player_id']} (等级 {entry['score']})")
    
    # 演示批量更新
    player_scores = {
        "player1": 110.0,
        "player2": 105.0,
        "player3": 100.0
    }
    
    mock_redis.client.zadd = AsyncMock()
    mock_redis.client.zcard = AsyncMock(return_value=3)
    
    await rank_service.batch_update_ranks(RankType.LEVEL, player_scores)
    print(f"\n批量更新排行榜: {len(player_scores)} 个玩家")


async def demo_task_management():
    """演示任务管理系统"""
    print("\n" + "="*50)
    print("4. 任务管理系统演示")  
    print("="*50)
    
    from services.logic.tasks.task_manager import TaskManager, scheduled_task, distributed_lock
    from unittest.mock import AsyncMock, MagicMock
    
    # 创建模拟Redis客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    
    # 创建任务管理器
    task_manager = TaskManager(mock_redis)
    
    # 定义带有定时任务的类
    class GameTasks:
        @scheduled_task(cron="0 0 * * *", description="每日签到重置")
        async def daily_checkin_reset(self):
            print("  执行每日签到重置...")
            
        @scheduled_task(cron="0 5 * * *", description="每日商店刷新")
        async def daily_shop_refresh(self):
            print("  执行每日商店刷新...")
            
        @scheduled_task(cron="*/30 * * * *", description="排行榜快照")
        async def ranking_snapshot(self):
            print("  创建排行榜快照...")
    
    # 注册定时任务
    game_tasks = GameTasks()
    task_manager.register_scheduled_task(game_tasks)
    
    print("已注册的定时任务:")
    for name, info in task_manager.scheduled_tasks.items():
        print(f"  {name}: {info['description']}")
        print(f"    Cron表达式: {info['cron']}")
        print(f"    下次执行: {info['next_run']}")
    
    # 演示延迟任务
    mock_redis.client.zadd = AsyncMock()
    
    task_id = await task_manager.add_delayed_task(
        {"type": "energy_recovery", "player_id": "demo_player"}, 
        300  # 5分钟后执行
    )
    print(f"\n添加延迟任务: {task_id} (5分钟后恢复体力)")
    
    # 演示分布式锁
    mock_redis.client.set = AsyncMock(return_value=True)
    mock_redis.client.eval = AsyncMock(return_value=1)
    
    print(f"\n演示分布式锁:")
    async with distributed_lock("demo_lock", redis_client=mock_redis):
        print("  获取分布式锁成功，执行临界区操作...")
        await asyncio.sleep(0.1)  # 模拟操作
    print("  释放分布式锁")


async def demo_player_handler():
    """演示玩家处理器"""
    print("\n" + "="*50)
    print("5. 玩家处理器演示")
    print("="*50)
    
    from services.logic.handlers.player_handler import PlayerHandler
    from common.protocol.messages.auth.login_request import LoginRequest
    from common.protocol.messages.player.player_info_request import PlayerInfoRequest
    from common.protocol.core.message_type import MessageType
    from unittest.mock import AsyncMock, MagicMock
    
    # 创建玩家处理器
    handler = PlayerHandler()
    
    # 模拟服务依赖
    handler.player_service = AsyncMock()
    handler.rank_service = AsyncMock()
    
    # 设置模拟返回值
    mock_player_data = {
        "player_id": "player_demo",
        "nickname": "演示玩家",
        "level": 5,
        "gold": 2500,
        "diamond": 150,
        "energy": 80,
        "vip_level": 1
    }
    
    handler.player_service.get_or_create = AsyncMock(return_value=MagicMock())
    handler.player_service.update_login_info = AsyncMock(
        return_value={"is_daily_first": True, "login_reward": 100}
    )
    handler.player_service.recover_energy = AsyncMock(return_value={"success": True})
    handler.player_service.get_by_id = AsyncMock(return_value=mock_player_data)
    handler.rank_service.update_level_rank = AsyncMock()
    handler.rank_service.update_wealth_rank = AsyncMock()
    handler.rank_service.get_rank = AsyncMock(return_value=42)
    
    # 演示登录处理
    print("演示玩家登录处理:")
    login_req = LoginRequest()
    login_req.username = "demouser"
    login_req.password = "demopass"
    login_req.device_id = "demo_device"
    login_req.platform = "demo"
    login_req.MESSAGE_TYPE = MessageType.LOGIN_REQUEST
    
    login_response = await handler.handle_login(login_req)
    print(f"  登录结果: 代码={login_response.code}, 消息={login_response.message}")
    print(f"  玩家ID: {login_response.player_id}")
    print(f"  在线玩家数: {handler.get_online_count()}")
    
    # 演示玩家信息查询
    print(f"\n演示玩家信息查询:")
    info_req = PlayerInfoRequest()
    info_req.target_player_id = "player_demo"
    info_req.MESSAGE_TYPE = MessageType.PLAYER_INFO_REQUEST
    
    info_response = await handler.handle_player_info(info_req)
    print(f"  查询结果: 代码={info_response.code}")
    if info_response.player_info:
        player_info = info_response.player_info
        print(f"  玩家信息:")
        print(f"    昵称: {player_info.get('nickname')}")
        print(f"    等级: {player_info.get('level')}")
        print(f"    金币: {player_info.get('gold')}")
        print(f"    钻石: {player_info.get('diamond')}")
        print(f"    等级排名: {player_info.get('level_rank')}")


async def demo_complete_workflow():
    """演示完整的游戏流程"""
    print("\n" + "="*50)
    print("6. 完整游戏流程演示")
    print("="*50)
    
    from services.logic.main import LogicService
    
    # 创建Logic服务
    logic_service = LogicService()
    
    print("Logic服务组件:")
    print(f"  gRPC服务名: {logic_service._grpc_service_info.name}")
    print(f"  服务端口: {logic_service._grpc_service_info.port}")
    print(f"  gRPC方法数: {len(logic_service._grpc_service_info.methods)}")
    
    print(f"\n  可用的gRPC方法:")
    for method_name, method_info in logic_service._grpc_service_info.methods.items():
        print(f"    {method_name}: {method_info.description}")
    
    print(f"\n业务流程演示:")
    print(f"  1. 玩家登录 -> PlayerHandler.handle_login")
    print(f"  2. 查询玩家信息 -> gRPC.get_player_info")
    print(f"  3. 获得经验升级 -> PlayerService.add_experience")
    print(f"  4. 更新排行榜 -> RankService.update_level_rank")
    print(f"  5. 定时任务处理 -> TaskManager.daily_reset")
    print(f"  6. 玩家离线 -> PlayerHandler.handle_player_offline")


async def main():
    """主演示函数"""
    print("Logic服务完整功能演示")
    print("=" * 80)
    print("这个演示展示了Logic服务的所有核心功能和使用方法")
    
    try:
        await demo_handler_system()
        await demo_player_service()
        await demo_ranking_system()
        await demo_task_management()
        await demo_player_handler()
        await demo_complete_workflow()
        
        print("\n" + "="*80)
        print("🎉 Logic服务演示完成！")
        print("="*80)
        print("\n主要特性:")
        print("✓ Handler注解路由 - 自动注册和分发请求处理")
        print("✓ Repository数据访问 - 基于common框架的数据库操作")
        print("✓ 定时任务管理 - Cron表达式支持，分布式锁保护")
        print("✓ Redis排行榜 - 多种排行榜类型，分页查询，定时快照")
        print("✓ gRPC服务注册 - 自动服务发现和方法注册")
        print("✓ 优雅关闭 - 数据库连接管理，在线玩家处理")
        print("\n适用场景:")
        print("• 大型多人在线游戏后端")
        print("• 微服务架构的游戏服务")
        print("• 需要高并发和可扩展性的游戏系统")
        
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())