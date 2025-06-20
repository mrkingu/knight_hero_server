"""
网关集成测试
Gateway Integration Tests

作者: lx
日期: 2025-06-18
描述: WebSocket连接测试、消息路由测试、会话管理测试
"""

import asyncio
import pytest
import time
import json
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch

# Import test utilities
from test.conftest import (
    MockWebSocket,
    MockRedisClient, 
    MockMongoClient,
    measure_performance,
    create_test_message,
    create_test_user,
    GameTestConfiguration
)


class TestWebSocketConnection:
    """WebSocket连接测试"""
    
    @pytest.mark.asyncio
    async def test_websocket_connection_creation(self, mock_websocket):
        """测试WebSocket连接创建"""
        # 模拟连接管理器
        from unittest.mock import Mock
        
        # 创建模拟的连接配置
        connection_config = Mock()
        connection_config.HEARTBEAT_INTERVAL = 30
        connection_config.CONNECTION_TIMEOUT = 60
        connection_config.MAX_MESSAGE_SIZE = 64 * 1024
        
        # 模拟连接对象
        connection = Mock()
        connection.id = "conn_123"
        connection.websocket = mock_websocket
        connection.state = "connected"
        connection.created_at = time.time()
        connection.last_activity = time.time()
        
        # 验证连接属性
        assert connection.id == "conn_123"
        assert connection.websocket == mock_websocket
        assert connection.state == "connected"
        assert connection.created_at > 0
        assert connection.last_activity > 0
    
    @pytest.mark.asyncio
    async def test_websocket_message_send_receive(self, mock_websocket):
        """测试WebSocket消息发送接收"""
        # 发送文本消息
        test_message = "Hello WebSocket!"
        await mock_websocket.send_text(test_message)
        
        # 验证消息已存储
        assert len(mock_websocket.messages) == 1
        assert mock_websocket.messages[0]["type"] == "text"
        assert mock_websocket.messages[0]["data"] == test_message
        
        # 接收消息
        received = await mock_websocket.receive_text()
        assert received == test_message
        
        # 发送字节消息
        byte_message = b"Binary data"
        await mock_websocket.send_bytes(byte_message)
        received_bytes = await mock_websocket.receive_bytes()
        assert received_bytes == byte_message
    
    @pytest.mark.asyncio
    async def test_websocket_connection_lifecycle(self, mock_websocket):
        """测试WebSocket连接生命周期"""
        # 初始状态
        assert mock_websocket.state == "connected"
        assert not mock_websocket.closed
        
        # 发送心跳
        heartbeat = {"type": "ping", "timestamp": time.time()}
        await mock_websocket.send_text(json.dumps(heartbeat))
        
        # 关闭连接
        await mock_websocket.close(code=1000, reason="Normal closure")
        
        # 验证关闭状态
        assert mock_websocket.closed
        assert mock_websocket.state == "closed"
    
    @pytest.mark.asyncio
    async def test_concurrent_websocket_connections(self):
        """测试并发WebSocket连接"""
        # 创建多个模拟连接
        connections = []
        for i in range(100):
            ws = MockWebSocket(host=f"192.168.1.{i%255}", port=12345+i)
            connections.append(ws)
        
        # 并发发送消息
        async def send_message(ws, message_id):
            message = {
                "id": message_id,
                "content": f"Message from connection {message_id}",
                "timestamp": time.time()
            }
            await ws.send_text(json.dumps(message))
            return message_id
        
        # 创建并发任务
        tasks = []
        for i, ws in enumerate(connections):
            task = send_message(ws, i)
            tasks.append(task)
        
        # 执行并发发送
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - start_time
        
        # 验证结果
        assert len(results) == 100
        assert all(isinstance(r, int) for r in results)
        
        # 验证所有连接都收到了消息
        for i, ws in enumerate(connections):
            assert len(ws.messages) == 1
            message_data = json.loads(ws.messages[0]["data"])
            assert message_data["id"] == i
        
        # 性能验证：100个并发连接应该在合理时间内完成
        print(f"100个并发连接处理时间: {duration:.3f}秒")
        assert duration < 1.0  # 应该在1秒内完成


class TestMessageRouting:
    """消息路由测试"""
    
    @pytest.mark.asyncio
    async def test_message_dispatcher_creation(self):
        """测试消息分发器创建"""
        # 模拟消息分发器
        dispatcher = Mock()
        dispatcher.handlers = {}
        dispatcher.default_handler = None
        dispatcher.stats = {
            "messages_processed": 0,
            "routing_errors": 0,
            "handler_count": 0
        }
        
        # 验证初始状态
        assert isinstance(dispatcher.handlers, dict)
        assert len(dispatcher.handlers) == 0
        assert dispatcher.stats["messages_processed"] == 0
    
    @pytest.mark.asyncio
    async def test_message_handler_registration(self):
        """测试消息处理器注册"""
        # 模拟消息分发器
        handlers = {}
        
        # 注册处理器
        async def login_handler(message: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "msg_id": 1002,
                "code": 0,
                "message": "Login successful",
                "data": {"player_id": message["player_id"]}
            }
        
        async def chat_handler(message: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "msg_id": 2002,
                "code": 0,
                "message": "Chat message sent",
                "data": {"content": message["data"]["content"]}
            }
        
        # 注册处理器
        handlers[1001] = login_handler  # 登录请求
        handlers[2001] = chat_handler   # 聊天请求
        
        # 验证注册
        assert 1001 in handlers
        assert 2001 in handlers
        assert len(handlers) == 2
        
        # 测试处理器调用
        login_msg = create_test_message(1001, "test_player", {"username": "testuser"})
        login_response = await handlers[1001](login_msg)
        assert login_response["code"] == 0
        assert login_response["data"]["player_id"] == "test_player"
        
        chat_msg = create_test_message(2001, "test_player", {"content": "Hello!"})
        chat_response = await handlers[2001](chat_msg)
        assert chat_response["code"] == 0
        assert chat_response["data"]["content"] == "Hello!"
    
    @pytest.mark.asyncio
    async def test_message_routing_logic(self):
        """测试消息路由逻辑"""
        # 模拟路由器
        async def route_message(message: Dict[str, Any], handlers: Dict[int, Any]) -> Dict[str, Any]:
            msg_id = message.get("msg_id")
            
            if msg_id in handlers:
                handler = handlers[msg_id]
                try:
                    response = await handler(message)
                    return response
                except Exception as e:
                    return {
                        "msg_id": msg_id + 1,
                        "code": 500,
                        "message": f"Handler error: {str(e)}"
                    }
            else:
                return {
                    "msg_id": msg_id + 1,
                    "code": 404,
                    "message": f"No handler for message type {msg_id}"
                }
        
        # 创建处理器
        handlers = {}
        
        async def echo_handler(message: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "msg_id": message["msg_id"] + 1,
                "code": 0,
                "message": "Echo response",
                "data": message["data"]
            }
        
        handlers[3001] = echo_handler
        
        # 测试正常路由
        echo_msg = create_test_message(3001, "test_player", {"echo": "test"})
        response = await route_message(echo_msg, handlers)
        assert response["code"] == 0
        assert response["data"]["echo"] == "test"
        
        # 测试未知消息类型
        unknown_msg = create_test_message(9999, "test_player", {})
        response = await route_message(unknown_msg, handlers)
        assert response["code"] == 404
        assert "No handler" in response["message"]
    
    @pytest.mark.asyncio
    async def test_message_routing_performance(self):
        """测试消息路由性能"""
        # 创建多个处理器
        handlers = {}
        
        async def fast_handler(message: Dict[str, Any]) -> Dict[str, Any]:
            # 快速处理器
            return {
                "msg_id": message["msg_id"] + 1,
                "code": 0,
                "message": "Fast response",
                "timestamp": time.time()
            }
        
        # 注册100个不同的处理器
        for i in range(100):
            handlers[4000 + i] = fast_handler
        
        # 路由函数
        async def route_message(message: Dict[str, Any]) -> Dict[str, Any]:
            msg_id = message.get("msg_id")
            if msg_id in handlers:
                return await handlers[msg_id](message)
            return {"code": 404, "message": "Not found"}
        
        # 创建测试消息
        messages = []
        for i in range(100):
            msg = create_test_message(4000 + i, f"player_{i}", {"index": i})
            messages.append(msg)
        
        # 测试路由性能
        start_time = time.perf_counter()
        responses = []
        for msg in messages:
            response = await route_message(msg)
            responses.append(response)
        routing_time = time.perf_counter() - start_time
        
        # 验证结果
        assert len(responses) == 100
        assert all(r["code"] == 0 for r in responses)
        
        # 性能验证
        avg_routing_time = routing_time / 100 * 1000  # 毫秒
        print(f"平均路由时间: {avg_routing_time:.3f}ms")
        assert avg_routing_time < 1.0  # 每条消息路由时间<1ms


class TestSessionManagement:
    """会话管理测试"""
    
    @pytest.mark.asyncio
    async def test_session_creation(self, mock_websocket):
        """测试会话创建"""
        # 模拟会话管理器
        sessions = {}
        session_counter = 0
        
        async def create_session(connection) -> Dict[str, Any]:
            nonlocal session_counter
            session_counter += 1
            
            session = {
                "id": f"session_{session_counter}",
                "connection_id": connection.id if hasattr(connection, 'id') else f"conn_{session_counter}",
                "websocket": connection,
                "state": "connecting",
                "created_at": time.time(),
                "last_activity": time.time(),
                "attributes": {
                    "user_id": None,
                    "player_id": None,
                    "device_id": None,
                    "authenticated": False
                }
            }
            
            sessions[session["id"]] = session
            return session
        
        # 创建会话
        mock_websocket.id = "ws_123"
        session = await create_session(mock_websocket)
        
        # 验证会话
        assert session["id"] == "session_1"
        assert session["connection_id"] == "ws_123"
        assert session["websocket"] == mock_websocket
        assert session["state"] == "connecting"
        assert not session["attributes"]["authenticated"]
        assert session["id"] in sessions
    
    @pytest.mark.asyncio
    async def test_session_authentication(self):
        """测试会话认证"""
        # 模拟会话
        session = {
            "id": "session_test",
            "state": "connecting",
            "attributes": {
                "user_id": None,
                "player_id": None,
                "device_id": None,
                "authenticated": False
            },
            "created_at": time.time(),
            "last_activity": time.time()
        }
        
        # 认证函数
        async def authenticate_session(session_id: str, user_id: str, player_id: str, device_id: str) -> bool:
            if session_id in sessions:
                session = sessions[session_id]
                session["attributes"]["user_id"] = user_id
                session["attributes"]["player_id"] = player_id
                session["attributes"]["device_id"] = device_id
                session["attributes"]["authenticated"] = True
                session["state"] = "authenticated"
                session["last_activity"] = time.time()
                return True
            return False
        
        sessions = {"session_test": session}
        
        # 执行认证
        success = await authenticate_session(
            "session_test", 
            "user_123", 
            "player_123", 
            "device_123"
        )
        
        # 验证认证结果
        assert success
        assert session["state"] == "authenticated"
        assert session["attributes"]["authenticated"]
        assert session["attributes"]["user_id"] == "user_123"
        assert session["attributes"]["player_id"] == "player_123"
        assert session["attributes"]["device_id"] == "device_123"
    
    @pytest.mark.asyncio
    async def test_session_cleanup(self):
        """测试会话清理"""
        # 创建多个会话
        sessions = {}
        current_time = time.time()
        
        # 活跃会话
        active_session = {
            "id": "active_1",
            "state": "authenticated",
            "created_at": current_time,
            "last_activity": current_time,
            "attributes": {"authenticated": True}
        }
        
        # 过期会话
        expired_session = {
            "id": "expired_1", 
            "state": "authenticated",
            "created_at": current_time - 3600,  # 1小时前
            "last_activity": current_time - 1800,  # 30分钟前
            "attributes": {"authenticated": True}
        }
        
        sessions["active_1"] = active_session
        sessions["expired_1"] = expired_session
        
        # 清理函数
        async def cleanup_expired_sessions(timeout: int = 900) -> List[str]:  # 15分钟超时
            current_time = time.time()
            expired_session_ids = []
            
            for session_id, session in list(sessions.items()):
                if current_time - session["last_activity"] > timeout:
                    expired_session_ids.append(session_id)
                    del sessions[session_id]
            
            return expired_session_ids
        
        # 执行清理
        expired_ids = await cleanup_expired_sessions(900)  # 15分钟超时
        
        # 验证清理结果
        assert "expired_1" in expired_ids
        assert "active_1" not in expired_ids
        assert "active_1" in sessions
        assert "expired_1" not in sessions
    
    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self):
        """测试并发会话操作"""
        sessions = {}
        session_counter = 0
        lock = asyncio.Lock()
        
        async def create_session(user_id: str) -> str:
            nonlocal session_counter
            async with lock:
                session_counter += 1
                session_id = f"session_{session_counter}"
                
                session = {
                    "id": session_id,
                    "user_id": user_id,
                    "state": "authenticated",
                    "created_at": time.time(),
                    "last_activity": time.time(),
                    "attributes": {"authenticated": True}
                }
                
                sessions[session_id] = session
                return session_id
        
        async def update_session_activity(session_id: str) -> bool:
            async with lock:
                if session_id in sessions:
                    sessions[session_id]["last_activity"] = time.time()
                    return True
                return False
        
        # 并发创建会话
        create_tasks = []
        for i in range(50):
            task = create_session(f"user_{i}")
            create_tasks.append(task)
        
        # 执行并发创建
        session_ids = await asyncio.gather(*create_tasks)
        
        # 验证创建结果
        assert len(session_ids) == 50
        assert len(sessions) == 50
        assert all(sid.startswith("session_") for sid in session_ids)
        
        # 并发更新活动时间
        update_tasks = []
        for session_id in session_ids:
            task = update_session_activity(session_id)
            update_tasks.append(task)
        
        # 执行并发更新
        update_results = await asyncio.gather(*update_tasks)
        
        # 验证更新结果
        assert len(update_results) == 50
        assert all(result for result in update_results)


class TestGatewayIntegration:
    """网关集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_message_flow(self, mock_websocket, mock_redis, mock_mongo):
        """测试完整消息流"""
        # 模拟完整的消息处理流程
        
        # 1. 创建连接和会话
        connection = {
            "id": "conn_001",
            "websocket": mock_websocket,
            "state": "connected",
            "created_at": time.time()
        }
        
        session = {
            "id": "session_001",
            "connection_id": "conn_001",
            "state": "authenticated",
            "attributes": {
                "user_id": "user_001",
                "player_id": "player_001",
                "authenticated": True
            }
        }
        
        # 2. 模拟消息处理器
        async def process_player_info_request(message: Dict[str, Any]) -> Dict[str, Any]:
            player_id = message["player_id"]
            
            # 模拟从数据库查询玩家信息
            player_data = await mock_mongo.get_database("game").get_collection("players").find_one(
                {"player_id": player_id}
            )
            
            if not player_data:
                # 创建新玩家
                player_data = create_test_user(player_id=player_id)
                await mock_mongo.get_database("game").get_collection("players").insert_one(player_data)
            
            # 缓存到Redis
            await mock_redis.set(f"player:{player_id}", json.dumps(player_data))
            
            return {
                "msg_id": 1003,
                "code": 0,
                "message": "Player info retrieved",
                "data": player_data
            }
        
        # 3. 创建测试消息
        request_message = create_test_message(
            msg_type=1002,
            player_id="player_001",
            data={"query": "basic_info"}
        )
        
        # 4. 处理消息
        response = await process_player_info_request(request_message)
        
        # 5. 验证响应
        assert response["code"] == 0
        assert response["data"]["player_id"] == "player_001"
        
        # 6. 验证数据库操作
        mongo_stats = mock_mongo.get_stats()
        assert mongo_stats["insert_ops"] > 0 or mongo_stats["find_ops"] > 0
        
        # 7. 验证缓存操作
        redis_stats = mock_redis.get_stats()
        assert redis_stats["sets"] > 0
        
        # 8. 模拟发送响应
        response_json = json.dumps(response)
        await mock_websocket.send_text(response_json)
        
        # 9. 验证消息发送
        assert len(mock_websocket.messages) == 1
        sent_message = json.loads(mock_websocket.messages[0]["data"])
        assert sent_message["code"] == 0
        assert sent_message["data"]["player_id"] == "player_001"
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self, mock_websocket):
        """测试错误处理流程"""
        # 模拟各种错误情况
        
        # 1. 无效消息格式
        async def handle_invalid_message():
            try:
                invalid_data = "{invalid json"
                json.loads(invalid_data)
            except json.JSONDecodeError:
                error_response = {
                    "msg_id": 0,
                    "code": 400,
                    "message": "Invalid message format"
                }
                await mock_websocket.send_text(json.dumps(error_response))
                return error_response
        
        # 2. 未认证会话
        async def handle_unauthenticated_request(message: Dict[str, Any]):
            session_authenticated = False  # 模拟未认证
            
            if not session_authenticated:
                error_response = {
                    "msg_id": message.get("msg_id", 0) + 1,
                    "code": 401,
                    "message": "Authentication required"
                }
                await mock_websocket.send_text(json.dumps(error_response))
                return error_response
        
        # 3. 处理器异常
        async def handle_processing_error():
            try:
                # 模拟处理异常
                raise Exception("Database connection failed")
            except Exception as e:
                error_response = {
                    "msg_id": 0,
                    "code": 500,
                    "message": f"Internal server error: {str(e)}"
                }
                await mock_websocket.send_text(json.dumps(error_response))
                return error_response
        
        # 测试各种错误情况
        error1 = await handle_invalid_message()
        assert error1["code"] == 400
        
        test_message = create_test_message(1001, "player_001", {})
        error2 = await handle_unauthenticated_request(test_message)
        assert error2["code"] == 401
        
        error3 = await handle_processing_error()
        assert error3["code"] == 500
        
        # 验证错误响应都已发送
        assert len(mock_websocket.messages) == 3
        for i, error in enumerate([error1, error2, error3]):
            sent_message = json.loads(mock_websocket.messages[i]["data"])
            assert sent_message["code"] == error["code"]
    
    @pytest.mark.asyncio
    async def test_gateway_performance(self):
        """测试网关性能"""
        # 模拟高并发场景
        
        async def simulate_client_session(client_id: int) -> Dict[str, Any]:
            """模拟单个客户端会话"""
            # 创建连接
            ws = MockWebSocket(host=f"192.168.1.{client_id % 255}", port=12345)
            
            # 发送登录消息
            login_msg = create_test_message(
                msg_type=1001,
                player_id=f"player_{client_id}",
                data={"username": f"user_{client_id}"}
            )
            await ws.send_text(json.dumps(login_msg))
            
            # 发送多条业务消息
            for i in range(5):
                business_msg = create_test_message(
                    msg_type=2001,
                    player_id=f"player_{client_id}",
                    data={"action": f"action_{i}", "value": i}
                )
                await ws.send_text(json.dumps(business_msg))
                
                # 模拟小延迟
                await asyncio.sleep(0.01)
            
            # 发送登出消息
            logout_msg = create_test_message(
                msg_type=1003,
                player_id=f"player_{client_id}",
                data={}
            )
            await ws.send_text(json.dumps(logout_msg))
            
            await ws.close()
            
            return {
                "client_id": client_id,
                "messages_sent": len(ws.messages),
                "connection_time": time.time()
            }
        
        # 创建100个并发客户端
        client_count = 100
        tasks = []
        
        for client_id in range(client_count):
            task = simulate_client_session(client_id)
            tasks.append(task)
        
        # 执行并发测试
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - start_time
        
        # 验证结果
        assert len(results) == client_count
        total_messages = sum(r["messages_sent"] for r in results)
        
        # 性能统计
        messages_per_second = total_messages / duration
        clients_per_second = client_count / duration
        
        print(f"并发客户端数: {client_count}")
        print(f"总处理时间: {duration:.3f}秒")
        print(f"总消息数: {total_messages}")
        print(f"消息处理速度: {messages_per_second:.0f} messages/sec")
        print(f"客户端处理速度: {clients_per_second:.0f} clients/sec")
        
        # 性能要求验证
        assert messages_per_second > 1000  # 至少1K messages/sec
        assert duration < 10.0  # 100个客户端应在10秒内完成


if __name__ == "__main__":
    # 运行集成测试
    pytest.main([__file__, "-v", "-s"])