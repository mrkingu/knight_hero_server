"""
Logic服务测试
Logic Service Tests

作者: lx
日期: 2025-06-20
描述: Logic服务的单元测试
"""

import asyncio
import pytest
import time
import json
from unittest.mock import AsyncMock, MagicMock

# 导入被测试的模块
from services.logic.handlers.base_handler import BaseHandler, handler, get_handler_registry
from services.logic.services.player_service import PlayerService
from services.logic.ranking.rank_service import RankService, RankType
from services.logic.tasks.task_manager import TaskManager, scheduled_task, distributed_lock
from services.logic.handlers.player_handler import PlayerHandler
from common.protocol.messages.auth.login_request import LoginRequest
from common.protocol.messages.auth.login_response import LoginResponse
from common.protocol.core.message_type import MessageType


class TestBaseHandler:
    """测试Handler基类"""
    
    def test_handler_decorator(self):
        """测试@handler装饰器"""
        
        class TestHandler(BaseHandler):
            @handler(cmd=1001)
            async def test_method(self, req):
                return {"success": True}
        
        # 检查装饰器是否正确设置
        assert hasattr(TestHandler.test_method, '_handler_cmd')
        assert TestHandler.test_method._handler_cmd == 1001
        
        # 检查注册表
        registry = get_handler_registry()
        assert 1001 in registry
    
    @pytest.mark.asyncio
    async def test_handler_validation(self):
        """测试请求验证"""
        handler = BaseHandler()
        
        # 模拟请求对象
        valid_request = MagicMock()
        valid_request.validate = MagicMock(return_value=True)
        
        invalid_request = MagicMock()
        invalid_request.validate = MagicMock(return_value=False)
        
        # 测试验证
        assert await handler._validate_request(valid_request) == True
        assert await handler._validate_request(invalid_request) == False
    
    def test_error_response_creation(self):
        """测试错误响应创建"""
        handler = BaseHandler()
        
        # 模拟请求
        request = MagicMock()
        request.MESSAGE_TYPE = 1001
        
        # 创建错误响应
        response = handler._create_error_response(request, 400, "测试错误")
        
        assert response.code == 400
        assert response.message == "测试错误"
        assert response.MESSAGE_TYPE == -1001


class TestPlayerService:
    """测试玩家服务"""
    
    @pytest.fixture
    def mock_redis(self):
        """模拟Redis客户端"""
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        return redis_mock
    
    @pytest.fixture
    def mock_mongo(self):
        """模拟MongoDB客户端"""
        return AsyncMock()
    
    @pytest.fixture
    def player_service(self, mock_redis, mock_mongo):
        """创建玩家服务实例"""
        return PlayerService(mock_redis, mock_mongo)
    
    @pytest.mark.asyncio
    async def test_get_or_create_new_player(self, player_service):
        """测试获取或创建新玩家"""
        # 模拟玩家不存在
        player_service.get_by_id = AsyncMock(return_value=None)
        player_service.create = AsyncMock()
        
        player = await player_service.get_or_create("test_player", nickname="测试玩家")
        
        assert player.player_id == "test_player"
        assert player.nickname == "测试玩家"
        assert player.level == 1
        assert player.gold == 1000  # 初始金币
        assert player.energy == 100  # 初始体力
    
    @pytest.mark.asyncio
    async def test_add_experience_with_level_up(self, player_service):
        """测试添加经验值和升级"""
        # 模拟当前玩家数据
        player_data = {
            "level": 1,
            "exp": 50,
            "gold": 1000
        }
        
        player_service.get_by_id = AsyncMock(return_value=player_data)
        player_service.increment = AsyncMock(return_value={"success": True})
        player_service.update = AsyncMock()
        player_service.add_gold = AsyncMock()
        
        # 添加足够升级的经验
        result = await player_service.add_experience("test_player", 150, "test")
        
        assert result["success"] == True
        assert result["level_up"] == True
        assert result["new_level"] == 2
        assert result["level_reward"] == 50


class TestRankService:
    """测试排行榜服务"""
    
    @pytest.fixture
    def mock_redis(self):
        """模拟Redis客户端"""
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        return redis_mock
    
    @pytest.fixture
    def rank_service(self, mock_redis):
        """创建排行榜服务实例"""
        return RankService(mock_redis)
    
    @pytest.mark.asyncio
    async def test_update_rank(self, rank_service):
        """测试更新排名"""
        rank_service.redis.client.zadd = AsyncMock()
        rank_service.redis.client.setex = AsyncMock()
        rank_service.redis.client.zcard = AsyncMock(return_value=10)
        
        result = await rank_service.update_rank(
            RankType.LEVEL, 
            "player1", 
            50.0,
            {"nickname": "测试玩家"}
        )
        
        assert result == True
        rank_service.redis.client.zadd.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_top_players(self, rank_service):
        """测试获取排行榜"""
        # 模拟Redis返回数据
        mock_data = [("player1", 100.0), ("player2", 90.0), ("player3", 80.0)]
        rank_service.redis.client.zrevrange = AsyncMock(return_value=mock_data)
        rank_service.redis.client.get = AsyncMock(return_value=None)
        
        result = await rank_service.get_top_players(RankType.LEVEL, 0, 3, False)
        
        assert len(result) == 3
        assert result[0]["rank"] == 1
        assert result[0]["player_id"] == "player1"
        assert result[0]["score"] == 100


class TestTaskManager:
    """测试任务管理器"""
    
    @pytest.fixture
    def mock_redis(self):
        """模拟Redis客户端"""
        redis_mock = AsyncMock()
        redis_mock.client = AsyncMock()
        return redis_mock
    
    @pytest.fixture
    def task_manager(self, mock_redis):
        """创建任务管理器实例"""
        return TaskManager(mock_redis)
    
    def test_scheduled_task_decorator(self):
        """测试定时任务装饰器"""
        
        class TestTasks:
            @scheduled_task(cron="0 0 * * *", description="每日任务")
            async def daily_task(self):
                pass
        
        # 检查装饰器属性
        assert hasattr(TestTasks.daily_task, '_is_scheduled_task')
        assert TestTasks.daily_task._cron_expression == "0 0 * * *"
        assert TestTasks.daily_task._task_description == "每日任务"
    
    @pytest.mark.asyncio
    async def test_add_delayed_task(self, task_manager):
        """测试添加延迟任务"""
        task_manager.redis.client.zadd = AsyncMock()
        
        task_id = await task_manager.add_delayed_task(
            {"type": "test", "data": "test_data"}, 
            60
        )
        
        assert task_id is not None
        task_manager.redis.client.zadd.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_distributed_lock(self, mock_redis):
        """测试分布式锁"""
        mock_redis.client.set = AsyncMock(return_value=True)
        mock_redis.client.eval = AsyncMock(return_value=1)
        
        async with distributed_lock("test_lock", redis_client=mock_redis):
            # 在锁内执行操作
            pass
        
        # 验证获取和释放锁的调用
        mock_redis.client.set.assert_called_once()
        mock_redis.client.eval.assert_called_once()


class TestPlayerHandler:
    """测试玩家处理器"""
    
    @pytest.fixture
    def player_handler(self):
        """创建玩家处理器实例"""
        handler = PlayerHandler()
        # 模拟服务依赖
        handler.player_service = AsyncMock()
        handler.rank_service = AsyncMock()
        return handler
    
    @pytest.mark.asyncio
    async def test_handle_login_success(self, player_handler):
        """测试成功登录"""
        # 创建登录请求
        login_req = LoginRequest()
        login_req.username = "testuser"
        login_req.password = "testpass"
        login_req.device_id = "device123"
        login_req.platform = "test"
        login_req.MESSAGE_TYPE = MessageType.LOGIN_REQUEST
        
        # 模拟服务调用
        mock_player_data = {
            "player_id": "player_testuser",
            "nickname": "testuser",
            "level": 1,
            "gold": 1000,
            "diamond": 0
        }
        
        player_handler.player_service.get_or_create = AsyncMock(return_value=MagicMock())
        player_handler.player_service.update_login_info = AsyncMock(
            return_value={"is_daily_first": True, "login_reward": 100}
        )
        player_handler.player_service.recover_energy = AsyncMock(return_value={"success": True})
        player_handler.player_service.get_by_id = AsyncMock(return_value=mock_player_data)
        player_handler.rank_service.update_level_rank = AsyncMock()
        player_handler.rank_service.update_wealth_rank = AsyncMock()
        
        # 执行登录
        response = await player_handler.handle_login(login_req)
        
        # 验证响应
        assert isinstance(response, LoginResponse)
        assert response.code == 0
        assert response.player_id == "player_testuser"
        assert "登录成功" in response.message
    
    @pytest.mark.asyncio
    async def test_handle_login_validation_failure(self, player_handler):
        """测试登录验证失败"""
        # 创建无效的登录请求
        login_req = LoginRequest()
        login_req.username = "a"  # 用户名太短
        login_req.password = ""   # 密码为空
        login_req.MESSAGE_TYPE = MessageType.LOGIN_REQUEST
        
        # 执行登录
        response = await player_handler.handle_login(login_req)
        
        # 验证响应
        assert isinstance(response, LoginResponse)
        assert response.code == 401
        assert "验证失败" in response.message
    
    def test_online_player_management(self, player_handler):
        """测试在线玩家管理"""
        # 初始状态
        assert player_handler.get_online_count() == 0
        
        # 添加在线玩家
        player_handler.online_players["player1"] = {
            "login_time": "2025-06-20T10:00:00",
            "last_activity": time.time()
        }
        
        assert player_handler.get_online_count() == 1
        assert "player1" in player_handler.get_online_players()


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_player_flow(self):
        """测试完整的玩家流程"""
        # 这里可以测试完整的玩家登录->游戏->离线流程
        # 由于依赖较多，这里只做基本的流程验证
        
        # 创建处理器
        handler = PlayerHandler()
        
        # 模拟依赖
        handler.player_service = AsyncMock()
        handler.rank_service = AsyncMock()
        
        # 模拟登录流程
        login_req = LoginRequest()
        login_req.username = "integration_test"
        login_req.password = "testpass"
        login_req.device_id = "device123"
        login_req.platform = "test"
        login_req.MESSAGE_TYPE = MessageType.LOGIN_REQUEST
        
        # 设置模拟返回值
        handler.player_service.get_or_create = AsyncMock(return_value=MagicMock())
        handler.player_service.update_login_info = AsyncMock(
            return_value={"is_daily_first": False, "login_reward": 0}
        )
        handler.player_service.recover_energy = AsyncMock(return_value={"success": True})
        handler.player_service.get_by_id = AsyncMock(return_value={
            "player_id": "player_integration_test",
            "nickname": "integration_test",
            "level": 5,
            "gold": 2000,
            "diamond": 100
        })
        
        # 执行登录
        response = await handler.handle_login(login_req)
        
        # 验证登录成功
        assert response.code == 0
        assert response.player_id == "player_integration_test"
        
        # 验证在线状态
        assert handler.get_online_count() == 1


# 运行测试的辅助函数
def run_tests():
    """运行所有测试"""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()