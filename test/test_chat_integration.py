"""
聊天服务端到端测试
Chat Service End-to-End Test

作者: lx
日期: 2025-06-18
描述: 测试聊天服务与网关的集成功能
"""
import asyncio
import time
from typing import Dict, Any

from services.chat.main import get_chat_service
from services.gateway.chat_integration import get_chat_integration


class MockSession:
    """模拟会话对象"""
    
    def __init__(self, user_id: str, nickname: str = None):
        self.id = f"session_{user_id}"
        self.is_authenticated = True
        
        class Attributes:
            def __init__(self, user_id: str, nickname: str = None):
                self.user_id = user_id
                self.nickname = nickname or user_id
        
        self.attributes = Attributes(user_id, nickname)


class MockConnection:
    """模拟连接对象"""
    
    def __init__(self):
        self.sent_messages = []
    
    async def send_dict(self, message: Dict[str, Any], message_type: str = None):
        """模拟发送消息"""
        self.sent_messages.append(message)
        print(f"发送消息: {message}")


class MockMessage:
    """模拟消息对象"""
    
    def __init__(self, message_type: str, data: Dict[str, Any]):
        self.type = message_type
        self.data = data


async def test_chat_service_basic():
    """测试聊天服务基础功能"""
    print("=== 测试聊天服务基础功能 ===")
    
    try:
        # 获取聊天服务
        chat_service = await get_chat_service()
        
        # 测试发送消息
        request_data = {
            "action": "send_message",
            "data": {
                "sender_id": "player1",
                "sender_name": "测试玩家1",
                "chat_type": 1,  # WORLD
                "content": "Hello World!",
                "channel": "world"
            }
        }
        
        response = await chat_service.handle_message(request_data)
        print(f"发送消息响应: {response}")
        
        assert response["success"] is True
        assert "message_id" in response
        
        # 测试获取历史消息
        history_request = {
            "action": "get_history",
            "data": {
                "player_id": "player1",
                "channel": "world",
                "count": 10
            }
        }
        
        history_response = await chat_service.handle_message(history_request)
        print(f"历史消息响应: {history_response}")
        
        assert history_response["success"] is True
        assert "messages" in history_response
        
        print("✅ 聊天服务基础功能测试通过")
        
    except Exception as e:
        print(f"❌ 聊天服务基础功能测试失败: {e}")
        raise


async def test_chat_integration():
    """测试聊天集成功能"""
    print("=== 测试聊天集成功能 ===")
    
    try:
        # 获取聊天集成器
        integration = await get_chat_integration()
        
        # 创建模拟对象
        session = MockSession("player2", "测试玩家2")
        connection = MockConnection()
        
        # 测试发送聊天消息
        message = MockMessage("chat", {
            "action": "send_message",
            "chat_type": 1,
            "content": "集成测试消息",
            "channel": "world"
        })
        
        await integration.handle_chat_message(connection, session, message)
        
        # 检查响应
        assert len(connection.sent_messages) > 0
        response = connection.sent_messages[-1]
        assert response["type"] == "chat_response"
        assert response["action"] == "send_message"
        
        print("✅ 聊天集成功能测试通过")
        
    except Exception as e:
        print(f"❌ 聊天集成功能测试失败: {e}")
        raise


async def test_word_filter_integration():
    """测试敏感词过滤集成"""
    print("=== 测试敏感词过滤集成 ===")
    
    try:
        # 获取聊天服务
        chat_service = await get_chat_service()
        
        # 测试包含敏感词的消息
        request_data = {
            "action": "send_message",
            "data": {
                "sender_id": "player3",
                "sender_name": "测试玩家3",
                "chat_type": 1,  # WORLD
                "content": "这是一个包含傻逼的测试消息",
                "channel": "world"
            }
        }
        
        response = await chat_service.handle_message(request_data)
        print(f"敏感词过滤响应: {response}")
        
        assert response["success"] is True
        assert response.get("filtered") is True
        assert "detected_words" in response
        assert len(response["detected_words"]) > 0
        
        print("✅ 敏感词过滤集成测试通过")
        
    except Exception as e:
        print(f"❌ 敏感词过滤集成测试失败: {e}")
        raise


async def test_private_message():
    """测试私聊功能"""
    print("=== 测试私聊功能 ===")
    
    try:
        # 获取聊天服务
        chat_service = await get_chat_service()
        
        # 测试私聊消息
        request_data = {
            "action": "send_message",
            "data": {
                "sender_id": "player1",
                "sender_name": "测试玩家1",
                "chat_type": 2,  # PRIVATE
                "content": "这是一条私聊消息",
                "channel": "private",
                "receiver_id": "player2",
                "receiver_name": "测试玩家2"
            }
        }
        
        response = await chat_service.handle_message(request_data)
        print(f"私聊消息响应: {response}")
        
        assert response["success"] is True
        assert "message_id" in response
        
        print("✅ 私聊功能测试通过")
        
    except Exception as e:
        print(f"❌ 私聊功能测试失败: {e}")
        raise


async def test_channel_management():
    """测试频道管理功能"""
    print("=== 测试频道管理功能 ===")
    
    try:
        # 获取聊天服务
        chat_service = await get_chat_service()
        
        # 测试创建频道
        create_request = {
            "action": "create_channel",
            "data": {
                "creator_id": "player1",
                "channel_name": "测试频道",
                "description": "这是一个测试频道"
            }
        }
        
        create_response = await chat_service.handle_message(create_request)
        print(f"创建频道响应: {create_response}")
        
        assert create_response["success"] is True
        assert "channel_id" in create_response
        
        # 测试加入频道
        join_request = {
            "action": "join_channel",
            "data": {
                "player_id": "player2",
                "channel_name": "测试频道"
            }
        }
        
        join_response = await chat_service.handle_message(join_request)
        print(f"加入频道响应: {join_response}")
        
        assert join_response["success"] is True
        
        # 测试获取频道列表
        list_request = {
            "action": "get_channel_list",
            "data": {
                "player_id": "player1"
            }
        }
        
        list_response = await chat_service.handle_message(list_request)
        print(f"频道列表响应: {list_response}")
        
        assert list_response["success"] is True
        assert "channels" in list_response
        
        print("✅ 频道管理功能测试通过")
        
    except Exception as e:
        print(f"❌ 频道管理功能测试失败: {e}")
        raise


async def run_all_tests():
    """运行所有测试"""
    print("开始运行聊天服务端到端测试...\n")
    
    try:
        await test_chat_service_basic()
        print()
        
        await test_chat_integration()
        print()
        
        await test_word_filter_integration()
        print()
        
        await test_private_message()
        print()
        
        await test_channel_management()
        print()
        
        print("🎉 所有测试通过！聊天服务集成成功！")
        
    except Exception as e:
        print(f"💥 测试失败: {e}")
        raise


if __name__ == "__main__":
    # 运行测试
    asyncio.run(run_all_tests())