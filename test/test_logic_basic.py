"""
Logic服务基础功能测试
Basic Logic Service Functionality Tests

作者: lx
日期: 2025-06-20
描述: 验证Logic服务的基本功能和集成
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

# 设置基础日志
logging.basicConfig(level=logging.INFO)


def test_handler_registration():
    """测试处理器注册功能"""
    print("=== 测试处理器注册功能 ===")
    
    from services.logic.handlers.base_handler import get_handler_registry
    from services.logic.handlers.player_handler import PlayerHandler
    
    # 获取注册的处理器
    registry = get_handler_registry()
    
    print(f"已注册的处理器数量: {len(registry)}")
    for cmd, handler in registry.items():
        print(f"  命令 {cmd}: {handler.__name__}")
    
    # 验证关键处理器存在
    assert 1001 in registry, "登录处理器未注册"
    assert 2001 in registry, "玩家信息处理器未注册"
    assert 2002 in registry, "玩家更新处理器未注册"
    
    print("✓ 处理器注册测试通过")


def test_ranking_system():
    """测试排行榜系统"""
    print("\n=== 测试排行榜系统 ===")
    
    from services.logic.ranking.rank_service import RankService, RankType
    from common.database.core import RedisClient
    
    # 创建模拟的Redis客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    
    # 创建排行榜服务
    rank_service = RankService(mock_redis)
    
    # 验证排行榜类型
    print(f"支持的排行榜类型: {[rt.value for rt in RankType]}")
    
    # 验证配置
    for rank_type in RankType:
        config = rank_service.rank_configs[rank_type]
        print(f"  {rank_type.value}: key={config['key']}, max_size={config['max_size']}")
    
    print("✓ 排行榜系统测试通过")


def test_task_management():
    """测试任务管理系统"""
    print("\n=== 测试任务管理系统 ===")
    
    from services.logic.tasks.task_manager import TaskManager, scheduled_task
    from common.database.core import RedisClient
    
    # 创建模拟的Redis客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    
    # 创建任务管理器
    task_manager = TaskManager(mock_redis)
    
    # 测试装饰器
    class TestTasks:
        @scheduled_task(cron="0 0 * * *", description="测试每日任务")
        async def daily_test(self):
            pass
        
        @scheduled_task(cron="*/5 * * * *", description="测试定时任务")
        async def regular_test(self):
            pass
    
    # 注册任务
    test_tasks = TestTasks()
    task_manager.register_scheduled_task(test_tasks)
    
    print(f"已注册的定时任务数量: {len(task_manager.scheduled_tasks)}")
    for name, info in task_manager.scheduled_tasks.items():
        print(f"  {name}: {info['description']} - {info['cron']}")
    
    print("✓ 任务管理系统测试通过")


async def test_player_service():
    """测试玩家服务"""
    print("\n=== 测试玩家服务 ===")
    
    from services.logic.services.player_service import PlayerService
    from common.database.core import RedisClient, MongoClient
    
    # 创建模拟客户端
    mock_redis = MagicMock()
    mock_redis.client = AsyncMock()
    
    mock_mongo = MagicMock()
    
    # 创建玩家服务
    player_service = PlayerService(mock_redis, mock_mongo)
    
    # 模拟基础方法
    player_service.get_by_id = AsyncMock(return_value=None)
    player_service.create = AsyncMock()
    
    # 测试创建新玩家
    player = await player_service.get_or_create("test_player", nickname="测试玩家")
    
    print(f"创建的玩家信息:")
    print(f"  ID: {player.player_id}")
    print(f"  昵称: {player.nickname}")
    print(f"  等级: {player.level}")
    print(f"  金币: {player.gold}")
    print(f"  钻石: {player.diamond}")
    print(f"  体力: {player.energy}")
    
    # 验证初始值
    assert player.player_id == "test_player"
    assert player.nickname == "测试玩家"
    assert player.level == 1
    assert player.gold == 1000  # 初始金币
    assert player.energy == 100  # 初始体力
    
    print("✓ 玩家服务测试通过")


async def test_player_handler():
    """测试玩家处理器"""
    print("\n=== 测试玩家处理器 ===")
    
    from services.logic.handlers.player_handler import PlayerHandler
    from common.protocol.messages.auth.login_request import LoginRequest
    from common.protocol.core.message_type import MessageType
    
    # 创建处理器
    handler = PlayerHandler()
    
    # 模拟服务依赖
    handler.player_service = AsyncMock()
    handler.rank_service = AsyncMock()
    
    # 模拟玩家数据
    mock_player_data = {
        "player_id": "player_testuser",
        "nickname": "testuser",
        "level": 1,
        "gold": 1000,
        "diamond": 0,
        "energy": 100
    }
    
    # 设置模拟返回值
    handler.player_service.get_or_create = AsyncMock(return_value=MagicMock())
    handler.player_service.update_login_info = AsyncMock(
        return_value={"is_daily_first": True, "login_reward": 100}
    )
    handler.player_service.recover_energy = AsyncMock(return_value={"success": True})
    handler.player_service.get_by_id = AsyncMock(return_value=mock_player_data)
    handler.rank_service.update_level_rank = AsyncMock()
    handler.rank_service.update_wealth_rank = AsyncMock()
    
    # 创建登录请求
    login_req = LoginRequest()
    login_req.username = "testuser"
    login_req.password = "testpass"
    login_req.device_id = "device123"
    login_req.platform = "test"
    login_req.MESSAGE_TYPE = MessageType.LOGIN_REQUEST
    
    # 执行登录
    response = await handler.handle_login(login_req)
    
    print(f"登录响应:")
    print(f"  代码: {response.code}")
    print(f"  消息: {response.message}")
    print(f"  玩家ID: {response.player_id}")
    print(f"  在线玩家数: {handler.get_online_count()}")
    
    # 验证响应
    assert response.code == 0
    assert response.player_id == "player_testuser"
    assert handler.get_online_count() == 1
    
    print("✓ 玩家处理器测试通过")


def test_grpc_service_registration():
    """测试gRPC服务注册"""
    print("\n=== 测试gRPC服务注册 ===")
    
    from services.logic.main import LogicService
    
    # 创建服务实例
    service = LogicService()
    
    # 验证gRPC装饰器
    assert hasattr(service, '_grpc_service_info')
    service_info = service._grpc_service_info
    
    print(f"gRPC服务信息:")
    print(f"  服务名: {service_info.name}")
    print(f"  地址: {service_info.address}")
    print(f"  端口: {service_info.port}")
    print(f"  方法数量: {len(service_info.methods)}")
    
    for method_name, method_info in service_info.methods.items():
        print(f"    {method_name}: {method_info.description}")
    
    # 验证关键方法
    assert "get_player_info" in service_info.methods
    assert "update_player_level" in service_info.methods
    assert "add_resources" in service_info.methods
    assert "get_ranking" in service_info.methods
    assert "get_service_status" in service_info.methods
    
    print("✓ gRPC服务注册测试通过")


async def run_all_tests():
    """运行所有测试"""
    print("开始运行Logic服务功能测试...")
    
    try:
        test_handler_registration()
        test_ranking_system()
        test_task_management()
        await test_player_service()
        await test_player_handler()
        test_grpc_service_registration()
        
        print("\n" + "="*50)
        print("🎉 所有测试通过！Logic服务实现正确!")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_tests())