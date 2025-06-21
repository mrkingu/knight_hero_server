"""
测试配置文件
Test Configuration File

作者: lx
日期: 2025-06-18
描述: pytest fixtures、测试数据库初始化、Mock服务、测试配置
"""

import asyncio
import pytest
import pytest_asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock
import time
import uuid

# Mock classes for testing
class MockWebSocket:
    """模拟WebSocket连接"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 12345):
        self.client = Mock()
        self.client.host = host
        self.client.port = port
        self.state = "connected"
        self.messages = []
        self.closed = False
        
    async def accept(self):
        """接受连接"""
        return True
        
    async def send_text(self, data: str):
        """发送文本消息"""
        if not self.closed:
            self.messages.append({"type": "text", "data": data, "timestamp": time.time()})
            
    async def send_bytes(self, data: bytes):
        """发送字节消息"""
        if not self.closed:
            self.messages.append({"type": "bytes", "data": data, "timestamp": time.time()})
            
    async def receive_text(self) -> str:
        """接收文本消息"""
        if self.messages:
            msg = self.messages.pop(0)
            if msg["type"] == "text":
                return msg["data"]
        raise asyncio.TimeoutError("No message received")
        
    async def receive_bytes(self) -> bytes:
        """接收字节消息"""
        if self.messages:
            msg = self.messages.pop(0)
            if msg["type"] == "bytes":
                return msg["data"]
        raise asyncio.TimeoutError("No message received")
        
    async def close(self, code: int = 1000, reason: str = "Normal closure"):
        """关闭连接"""
        self.closed = True
        self.state = "closed"


class MockRedisClient:
    """模拟Redis客户端"""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.stats = {"hits": 0, "misses": 0, "sets": 0, "deletes": 0}
        
    async def get(self, key: str) -> Optional[bytes]:
        """获取值"""
        if key in self.data:
            self.stats["hits"] += 1
            value = self.data[key]
            if isinstance(value, str):
                return value.encode()
            return value
        self.stats["misses"] += 1
        return None
        
    async def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置值"""
        self.data[key] = value
        self.stats["sets"] += 1
        return True
        
    async def delete(self, *keys: str) -> int:
        """删除键"""
        deleted = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                deleted += 1
        self.stats["deletes"] += deleted
        return deleted
        
    async def exists(self, *keys: str) -> int:
        """检查键是否存在"""
        return sum(1 for key in keys if key in self.data)
        
    async def flushdb(self) -> bool:
        """清空数据库"""
        self.data.clear()
        return True
        
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()


class MockMongoClient:
    """模拟MongoDB客户端"""
    
    def __init__(self):
        self.databases: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.stats = {"insert_ops": 0, "update_ops": 0, "find_ops": 0, "delete_ops": 0}
        
    def get_database(self, name: str):
        """获取数据库"""
        if name not in self.databases:
            self.databases[name] = {}
        return MockDatabase(self.databases[name], self.stats)
        
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.stats.copy()


class MockDatabase:
    """模拟MongoDB数据库"""
    
    def __init__(self, collections: Dict[str, Dict[str, Any]], stats: Dict[str, int]):
        self.collections = collections
        self.stats = stats
        
    def get_collection(self, name: str):
        """获取集合"""
        if name not in self.collections:
            self.collections[name] = {}
        return MockCollection(self.collections[name], self.stats)


class MockCollection:
    """模拟MongoDB集合"""
    
    def __init__(self, documents: Dict[str, Any], stats: Dict[str, int]):
        self.documents = documents
        self.stats = stats
        
    async def insert_one(self, document: Dict[str, Any]) -> Any:
        """插入单个文档"""
        doc_id = document.get("_id", str(uuid.uuid4()))
        document["_id"] = doc_id
        self.documents[str(doc_id)] = document.copy()
        self.stats["insert_ops"] += 1
        
        result = Mock()
        result.inserted_id = doc_id
        return result
        
    async def find_one(self, filter_dict: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """查找单个文档"""
        self.stats["find_ops"] += 1
        filter_dict = filter_dict or {}
        
        for doc in self.documents.values():
            if self._match_filter(doc, filter_dict):
                return doc.copy()
        return None
        
    async def update_one(self, filter_dict: Dict[str, Any], update: Dict[str, Any]) -> Any:
        """更新单个文档"""
        self.stats["update_ops"] += 1
        
        for doc_id, doc in self.documents.items():
            if self._match_filter(doc, filter_dict):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for key, value in update["$inc"].items():
                        doc[key] = doc.get(key, 0) + value
                        
                result = Mock()
                result.modified_count = 1
                return result
                
        result = Mock()
        result.modified_count = 0
        return result
        
    async def delete_one(self, filter_dict: Dict[str, Any]) -> Any:
        """删除单个文档"""
        self.stats["delete_ops"] += 1
        
        for doc_id, doc in list(self.documents.items()):
            if self._match_filter(doc, filter_dict):
                del self.documents[doc_id]
                result = Mock()
                result.deleted_count = 1
                return result
                
        result = Mock()
        result.deleted_count = 0
        return result
        
    def _match_filter(self, doc: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        """匹配过滤条件"""
        for key, value in filter_dict.items():
            if key not in doc or doc[key] != value:
                return False
        return True


class GameTestConfiguration:
    """测试配置类"""
    
    def __init__(self):
        self.TEST_DATABASE_URL = "mock://test_database"
        self.TEST_REDIS_URL = "mock://test_redis"
        self.TEST_HOST = "127.0.0.1"
        self.TEST_PORT = 8888
        self.TEST_WEBSOCKET_URL = f"ws://{self.TEST_HOST}:{self.TEST_PORT}/ws"
        
        # 连接池配置
        self.MAX_CONNECTIONS = 1000
        self.POOL_SIZE = 100
        self.CONNECTION_TIMEOUT = 30
        
        # 测试用户配置
        self.TEST_USERS_COUNT = 100
        self.TEST_PLAYER_ID_PREFIX = "test_player_"
        self.TEST_USER_ID_PREFIX = "test_user_"


# Pytest fixtures
@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """测试配置fixture"""
    return GameTestConfiguration()


@pytest.fixture
async def mock_websocket():
    """Mock WebSocket fixture"""
    ws = MockWebSocket()
    yield ws
    await ws.close()


@pytest.fixture
async def mock_redis():
    """Mock Redis客户端fixture"""
    client = MockRedisClient()
    yield client
    await client.flushdb()


@pytest.fixture
async def mock_mongo():
    """Mock MongoDB客户端fixture"""
    client = MockMongoClient()
    yield client


@pytest.fixture
async def temp_directory():
    """临时目录fixture"""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    yield temp_path
    shutil.rmtree(temp_dir)


@pytest.fixture
async def mock_database_session(mock_mongo, mock_redis):
    """模拟数据库会话"""
    session = {
        "mongo": mock_mongo,
        "redis": mock_redis,
        "transaction_id": str(uuid.uuid4())
    }
    yield session


@pytest.fixture
def sample_player_data():
    """示例玩家数据"""
    return {
        "player_id": "test_player_123",
        "user_id": "test_user_123",
        "nickname": "TestPlayer",
        "level": 1,
        "exp": 0,
        "gold": 1000,
        "created_at": time.time(),
        "last_login": time.time()
    }


@pytest.fixture
def sample_game_config():
    """示例游戏配置数据"""
    return {
        "config_id": "test_config",
        "max_level": 100,
        "base_exp": 100,
        "exp_multiplier": 1.5,
        "starting_gold": 1000,
        "items": [
            {"id": 1001, "name": "小血瓶", "type": "consumable", "price": 50},
            {"id": 1002, "name": "魔法卷轴", "type": "consumable", "price": 100}
        ]
    }


@pytest.fixture
async def connection_manager_mock():
    """Mock连接管理器"""
    from unittest.mock import Mock, AsyncMock
    
    manager = Mock()
    manager.create_connection = AsyncMock()
    manager.remove_connection = AsyncMock()
    manager.get_connection = AsyncMock()
    manager.get_connection_count = Mock(return_value=0)
    manager.get_stats = Mock(return_value={
        "active_connections": 0,
        "total_created": 0,
        "total_destroyed": 0,
        "peak_concurrent": 0
    })
    
    yield manager


@pytest.fixture
async def session_manager_mock():
    """Mock会话管理器"""
    from unittest.mock import Mock, AsyncMock
    
    manager = Mock()
    manager.create_session = AsyncMock()
    manager.get_session = AsyncMock()
    manager.authenticate_session = AsyncMock()
    manager.remove_session = AsyncMock()
    manager.get_stats = Mock(return_value={
        "active_sessions": 0,
        "authenticated_sessions": 0,
        "total_created": 0
    })
    
    yield manager


@pytest.fixture
async def message_dispatcher_mock():
    """Mock消息分发器"""
    from unittest.mock import Mock, AsyncMock
    
    dispatcher = Mock()
    dispatcher.dispatch = AsyncMock()
    dispatcher.register_handler = Mock()
    dispatcher.unregister_handler = Mock()
    dispatcher.get_stats = Mock(return_value={
        "messages_processed": 0,
        "handlers_count": 0,
        "processing_time_ms": 0
    })
    
    yield dispatcher


# 性能测试辅助函数
async def measure_performance(func, *args, **kwargs):
    """测量函数执行性能"""
    start_time = time.perf_counter()
    result = await func(*args, **kwargs)
    end_time = time.perf_counter()
    
    return {
        "result": result,
        "execution_time": (end_time - start_time) * 1000,  # 毫秒
        "start_time": start_time,
        "end_time": end_time
    }


def create_test_user(user_id: str = None, player_id: str = None) -> Dict[str, Any]:
    """创建测试用户数据"""
    user_id = user_id or f"test_user_{uuid.uuid4().hex[:8]}"
    player_id = player_id or f"test_player_{uuid.uuid4().hex[:8]}"
    
    return {
        "user_id": user_id,
        "player_id": player_id,
        "nickname": f"TestUser_{user_id[-8:]}",
        "level": 1,
        "exp": 0,
        "gold": 1000,
        "device_id": f"device_{uuid.uuid4().hex[:8]}",
        "created_at": time.time(),
        "last_login": time.time()
    }


def create_test_message(msg_type: int = 1001, player_id: str = None, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """创建测试消息"""
    player_id = player_id or f"test_player_{uuid.uuid4().hex[:8]}"
    data = data or {"content": "test message"}
    
    return {
        "msg_id": msg_type,
        "player_id": player_id,
        "data": data,
        "timestamp": time.time(),
        "sequence": str(uuid.uuid4())
    }


# Pytest标记
pytest_plugins = []

# 异步测试配置
pytest_asyncio.default_fixture_loop_scope = 'function'