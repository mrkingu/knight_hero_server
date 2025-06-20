"""
Gateway服务测试模块
Gateway Service Test Module

作者: lx
日期: 2025-06-18
描述: 测试Gateway服务的各个组件功能
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock

from common.utils import SnowflakeIdGenerator, generate_id, parse_id
from services.gateway.connection import Connection, ConnectionConfig, ConnectionState, Message
from services.gateway.session import Session, SessionState, SessionAttributes
from services.gateway.connection_manager import ConnectionManager, ConnectionPoolConfig
from services.gateway.session_manager import SessionManager, SessionManagerConfig


class TestSnowflakeIdGenerator:
    """雪花算法ID生成器测试"""
    
    def test_id_generator_creation(self):
        """测试ID生成器创建"""
        generator = SnowflakeIdGenerator(datacenter_id=1, worker_id=1)
        assert generator.datacenter_id == 1
        assert generator.worker_id == 1
    
    def test_id_generation(self):
        """测试ID生成"""
        generator = SnowflakeIdGenerator()
        
        # 生成多个ID
        ids = [generator.generate_id() for _ in range(100)]
        
        # 验证ID唯一性
        assert len(set(ids)) == len(ids)
        
        # 验证ID递增性
        assert all(ids[i] < ids[i+1] for i in range(len(ids)-1))
    
    def test_id_parsing(self):
        """测试ID解析"""
        generator = SnowflakeIdGenerator(datacenter_id=5, worker_id=10)
        snowflake_id = generator.generate_id()
        
        parsed = generator.parse_id(snowflake_id)
        
        assert parsed['datacenter_id'] == 5
        assert parsed['worker_id'] == 10
        assert 'timestamp' in parsed
        assert 'datetime' in parsed
        assert 'sequence' in parsed
    
    def test_global_functions(self):
        """测试全局函数"""
        # 测试全局ID生成
        id1 = generate_id()
        id2 = generate_id()
        
        assert id1 != id2
        assert id1 < id2
        
        # 测试全局ID解析
        parsed = parse_id(id1)
        assert 'timestamp' in parsed


class TestSession:
    """会话对象测试"""
    
    def test_session_creation(self):
        """测试会话创建"""
        # 创建模拟连接
        mock_connection = Mock()
        
        session = Session(mock_connection)
        
        assert session.connection == mock_connection
        assert session.state == SessionState.CONNECTING
        assert session.id > 0
        assert isinstance(session.attributes, SessionAttributes)
        assert session.created_at > 0
    
    @pytest.mark.asyncio
    async def test_session_authentication(self):
        """测试会话认证"""
        mock_connection = Mock()
        session = Session(mock_connection)
        
        # 测试认证
        success = await session.authenticate(
            user_id="test_user",
            player_id="test_player",
            device_id="test_device"
        )
        
        assert success
        assert session.is_authenticated
        assert session.state == SessionState.AUTHENTICATED
        assert session.attributes.user_id == "test_user"
        assert session.attributes.player_id == "test_player"
        assert session.attributes.device_id == "test_device"
        assert session.expires_at is not None
    
    @pytest.mark.asyncio
    async def test_session_renewal(self):
        """测试会话续期"""
        mock_connection = Mock()
        session = Session(mock_connection)
        
        # 先认证
        await session.authenticate("test_user")
        old_expires_at = session.expires_at
        
        # 等待一小段时间
        await asyncio.sleep(0.1)
        
        # 续期（使用更长的时间以确保新的过期时间更大）
        success = await session.renew(60 * 60)  # 1小时
        
        assert success
        assert session.expires_at > old_expires_at
    
    def test_session_serialization(self):
        """测试会话序列化"""
        mock_connection = Mock()
        session = Session(mock_connection)
        
        # 设置一些属性
        session.attributes.user_id = "test_user"
        session.add_permission("read")
        session.add_role("user")
        
        # 序列化
        session_dict = session.to_dict()
        
        assert session_dict['id'] == str(session.id)
        assert session_dict['attributes']['user_id'] == "test_user"
        assert "read" in session_dict['permissions']
        assert "user" in session_dict['roles']


class TestConnection:
    """连接对象测试"""
    
    def test_connection_creation(self):
        """测试连接创建"""
        # 创建模拟WebSocket
        mock_websocket = Mock()
        mock_websocket.client.host = "127.0.0.1"
        mock_websocket.client.port = 12345
        
        config = ConnectionConfig()
        connection = Connection(mock_websocket, config)
        
        assert connection.websocket == mock_websocket
        assert connection.config == config
        assert connection.state == ConnectionState.IDLE
        assert connection.client_host == "127.0.0.1"
        assert connection.client_port == 12345
    
    @pytest.mark.asyncio
    async def test_connection_message_queues(self):
        """测试连接消息队列"""
        mock_websocket = Mock()
        connection = Connection(mock_websocket)
        
        # 创建测试消息
        message = Message(
            type="test",
            data={"content": "test message"},
            timestamp=time.time()
        )
        
        # 测试发送消息到队列
        success = await connection.send_message(message)
        assert not success  # 因为连接未建立，应该失败
        
        # 模拟连接建立
        connection.state = ConnectionState.CONNECTED
        success = await connection.send_message(message)
        assert success
        
        # 检查队列大小
        assert connection.write_queue.qsize() == 1
    
    def test_connection_stats(self):
        """测试连接统计"""
        mock_websocket = Mock()
        connection = Connection(mock_websocket)
        
        stats = connection.get_stats()
        
        assert 'id' in stats
        assert 'state' in stats
        assert 'bytes_sent' in stats
        assert 'bytes_received' in stats
        assert 'messages_sent' in stats
        assert 'messages_received' in stats


class TestConnectionManager:
    """连接管理器测试"""
    
    @pytest.mark.asyncio
    async def test_connection_manager_initialization(self):
        """测试连接管理器初始化"""
        config = ConnectionPoolConfig(
            POOL_SIZE=100,
            PRE_ALLOCATE_SIZE=10
        )
        
        manager = ConnectionManager(config)
        success = await manager.initialize()
        
        assert success
        assert manager._initialized
        assert len(manager.idle_connections) == config.PRE_ALLOCATE_SIZE
        
        # 清理
        await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_connection_pool_stats(self):
        """测试连接池统计"""
        manager = ConnectionManager()
        await manager.initialize()
        
        stats = manager.get_pool_stats()
        
        assert 'active_connections' in stats
        assert 'idle_connections' in stats
        assert 'total_created' in stats
        assert 'pool_hits' in stats
        assert 'pool_misses' in stats
        
        await manager.shutdown()


class TestSessionManager:
    """会话管理器测试"""
    
    @pytest.mark.asyncio
    async def test_session_manager_basic(self):
        """测试会话管理器基本功能"""
        # 注意：这个测试需要Redis连接，在CI环境中可能失败
        # 这里只测试基本初始化
        config = SessionManagerConfig(
            LOCAL_CACHE_SIZE=100
        )
        
        manager = SessionManager(config)
        
        # 测试缓存
        assert manager.local_cache.max_size == 100
        
        # 测试统计
        stats = manager.get_stats()
        assert 'active_sessions' in stats
        assert 'cached_sessions' in stats


def test_basic_imports():
    """测试基本导入功能"""
    # 测试所有模块都能正常导入
    from services.gateway.main import GatewayApp
    from services.gateway.connection import Connection, ConnectionConfig
    from services.gateway.session import Session, SessionState
    from services.gateway.connection_manager import ConnectionManager
    from services.gateway.session_manager import SessionManager
    from common.utils import SnowflakeIdGenerator
    
    assert GatewayApp is not None
    assert Connection is not None
    assert Session is not None
    assert ConnectionManager is not None
    assert SessionManager is not None
    assert SnowflakeIdGenerator is not None


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])