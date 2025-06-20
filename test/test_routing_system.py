"""
消息路由系统测试模块
Message Routing System Test Module

作者: lx
日期: 2025-06-18
描述: 测试消息路由系统的各个组件功能
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock

from common.protocol.core.base_request import BaseRequest
from common.protocol.core.message_type import MessageType
from services.gateway.router import MessageRouter, ServiceInstance, ConsistentHash, RouteCache
from services.gateway.message_queue import PriorityMessageQueue, MessagePriority, QueuedMessage
from services.gateway.message_dispatcher import MessageDispatcher, BatchConfig
from services.gateway.handlers import UnifiedMessageHandler, MessageCategory


class TestMessageRouter:
    """消息路由器测试"""
    
    def test_router_initialization(self):
        """测试路由器初始化"""
        router = MessageRouter()
        
        # 检查路由表是否正确编译
        assert 1000 in router._route_table
        assert router._route_table[1000] == "logic"
        assert router._route_table[2000] == "chat"
        assert router._route_table[3000] == "fight"
        assert router._route_table[9000] == "gateway"
    
    def test_service_instance_registration(self):
        """测试服务实例注册"""
        router = MessageRouter()
        
        instance = ServiceInstance("logic", "logic-1", "127.0.0.1", 50001)
        router.register_service_instance(instance)
        
        instances = router.get_service_instances("logic")
        assert len(instances) == 1
        assert instances[0].endpoint == "127.0.0.1:50001"
    
    @pytest.mark.asyncio
    async def test_message_routing(self):
        """测试消息路由"""
        router = MessageRouter()
        
        # 注册服务实例
        instance = ServiceInstance("logic", "logic-1", "127.0.0.1", 50001)
        router.register_service_instance(instance)
        
        # 创建测试消息
        message = BaseRequest()
        message.msg_id = 1001  # 逻辑服务消息
        message.player_id = "test_player"
        
        # 路由消息
        result_instance = await router.route_message(message)
        
        assert result_instance is not None
        assert result_instance.service_name == "logic"
        assert result_instance.endpoint == "127.0.0.1:50001"
    
    def test_consistent_hash(self):
        """测试一致性哈希"""
        hash_ring = ConsistentHash()
        
        # 添加实例
        instance1 = ServiceInstance("test", "test-1", "127.0.0.1", 50001)
        instance2 = ServiceInstance("test", "test-2", "127.0.0.1", 50002)
        
        hash_ring.add_instance(instance1)
        hash_ring.add_instance(instance2)
        
        # 测试哈希分布
        key1_instance = hash_ring.get_instance("player1")
        key2_instance = hash_ring.get_instance("player2")
        
        assert key1_instance is not None
        assert key2_instance is not None
        
        # 同一个key应该总是路由到同一个实例
        assert hash_ring.get_instance("player1") == key1_instance
    
    def test_route_cache(self):
        """测试路由缓存"""
        cache = RouteCache(max_size=100, ttl=60)
        
        # 测试缓存存取
        cache.put("test_key", "logic")
        assert cache.get("test_key") == "logic"
        
        # 测试缓存过期
        cache.put("expired_key", "chat")
        # 手动设置过期时间
        cache.cache["expired_key"] = ("chat", time.time() - 100)
        assert cache.get("expired_key") is None


class TestMessageQueue:
    """消息队列测试"""
    
    @pytest.mark.asyncio
    async def test_priority_queue_basic(self):
        """测试优先级队列基本功能"""
        queue = PriorityMessageQueue(max_size=100)
        
        # 创建测试消息
        message1 = BaseRequest()
        message1.msg_id = 1001
        
        message2 = BaseRequest()  
        message2.msg_id = 1002
        
        # 入队
        success1 = await queue.enqueue(message1, MessagePriority.HIGH)
        success2 = await queue.enqueue(message2, MessagePriority.LOW)
        
        assert success1
        assert success2
        assert queue.size() == 2
        
        # 出队 - 高优先级应该先出来
        queued_msg1 = await queue.dequeue(timeout=1.0)
        assert queued_msg1 is not None
        assert queued_msg1.priority == MessagePriority.HIGH
        
        queued_msg2 = await queue.dequeue(timeout=1.0)
        assert queued_msg2 is not None
        assert queued_msg2.priority == MessagePriority.LOW
    
    @pytest.mark.asyncio
    async def test_backpressure_control(self):
        """测试背压控制"""
        # 创建小容量队列测试背压
        queue = PriorityMessageQueue(max_size=5, enable_backpressure=True)
        
        messages = []
        for i in range(10):
            msg = BaseRequest()
            msg.msg_id = 1000 + i
            messages.append(msg)
        
        # 填满队列
        accepted = 0
        for msg in messages:
            if await queue.enqueue(msg, MessagePriority.NORMAL):
                accepted += 1
        
        # 应该有部分消息被拒绝
        assert accepted < len(messages)
        assert accepted <= 5
    
    @pytest.mark.asyncio
    async def test_message_deduplication(self):
        """测试消息去重"""
        queue = PriorityMessageQueue(enable_deduplication=True)
        
        # 创建相同的消息
        message1 = BaseRequest()
        message1.msg_id = 1001
        message1.sequence = "test_seq"
        
        message2 = BaseRequest()
        message2.msg_id = 1001  
        message2.sequence = "test_seq"  # 相同序列号
        
        # 第一次入队应该成功
        success1 = await queue.enqueue(message1)
        assert success1
        
        # 第二次入队应该被去重
        success2 = await queue.enqueue(message2)
        assert not success2
        
        assert queue.size() == 1


class TestMessageDispatcher:
    """消息分发器测试"""
    
    @pytest.mark.asyncio
    async def test_dispatcher_initialization(self):
        """测试分发器初始化"""
        router = MessageRouter()
        queue = PriorityMessageQueue()
        
        dispatcher = MessageDispatcher(router, queue)
        
        assert dispatcher.router == router
        assert dispatcher.queue == queue
        assert isinstance(dispatcher.batch_config, BatchConfig)
    
    @pytest.mark.asyncio
    async def test_batch_processor(self):
        """测试批处理器"""
        from services.gateway.message_dispatcher import BatchProcessor
        
        batch_config = BatchConfig(batch_size=3, timeout_ms=100)
        processor = BatchProcessor(batch_config)
        
        # 设置批处理回调
        processed_batches = []
        async def batch_handler(batch):
            processed_batches.append(batch)
        
        processor.set_batch_handler(batch_handler)
        
        # 添加消息
        messages = []
        for i in range(5):
            msg = BaseRequest()
            msg.msg_id = 1000 + i
            queued_msg = QueuedMessage(msg, MessagePriority.NORMAL, time.time())
            messages.append(queued_msg)
            await processor.add_message(queued_msg)
        
        # 强制刷新
        await processor.force_flush()
        
        # 应该产生至少一个批次
        assert len(processed_batches) > 0


class TestMessageHandlers:
    """消息处理器测试"""
    
    @pytest.mark.asyncio
    async def test_unified_handler_categorization(self):
        """测试统一处理器的消息分类"""
        router = MessageRouter()
        queue = PriorityMessageQueue()
        dispatcher = MessageDispatcher(router, queue)
        
        handler = UnifiedMessageHandler(dispatcher)
        
        # 测试系统消息分类
        system_msg = Mock()
        system_msg.type = "heartbeat"
        system_msg.msg_id = 0
        
        category = handler._categorize_message(system_msg)
        assert category == MessageCategory.SYSTEM
        
        # 测试业务消息分类
        business_msg = Mock()
        business_msg.type = ""
        business_msg.msg_id = 1001
        
        category = handler._categorize_message(business_msg)
        assert category == MessageCategory.BUSINESS
        
        # 测试网关消息分类
        gateway_msg = Mock()
        gateway_msg.type = ""
        gateway_msg.msg_id = 9001
        
        category = handler._categorize_message(gateway_msg)
        assert category == MessageCategory.GATEWAY
    
    @pytest.mark.asyncio
    async def test_system_message_handling(self):
        """测试系统消息处理"""
        from services.gateway.handlers import SystemMessageHandler
        
        handler = SystemMessageHandler()
        
        # 模拟连接和会话
        mock_connection = AsyncMock()
        mock_session = Mock()
        mock_session.update_ping = Mock()
        
        # 测试心跳处理
        await handler.handle_heartbeat(mock_connection, mock_session, {})
        
        mock_session.update_ping.assert_called_once()
        mock_connection.send_dict.assert_called_once()
        
        # 检查统计信息
        assert handler.stats.heartbeats == 1


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_flow(self):
        """测试端到端消息流程"""
        # 创建完整的路由系统
        router = MessageRouter()
        queue = PriorityMessageQueue()
        dispatcher = MessageDispatcher(router, queue)
        handler = UnifiedMessageHandler(dispatcher)
        
        # 注册服务实例
        instance = ServiceInstance("logic", "logic-1", "127.0.0.1", 50001)
        router.register_service_instance(instance)
        
        # 模拟连接和会话
        mock_connection = AsyncMock()
        mock_session = Mock()
        mock_session.is_authenticated = True
        mock_session.attributes.player_id = "test_player"
        mock_session.update_activity = Mock()
        
        # 创建业务消息
        message = BaseRequest()
        message.msg_id = 1001  # 逻辑服务消息
        message.player_id = "test_player"
        
        # 处理消息
        await handler.handle_message(mock_connection, mock_session, message)
        
        # 验证消息进入队列
        assert queue.size() > 0
        
        # 验证统计信息
        stats = handler.get_handler_stats()
        assert stats["total"]["total_received"] == 1
        assert stats["total"]["business_messages"] == 1


def test_basic_imports():
    """测试基本导入功能"""
    from services.gateway.router import MessageRouter, ServiceInstance
    from services.gateway.message_queue import PriorityMessageQueue, MessagePriority
    from services.gateway.message_dispatcher import MessageDispatcher
    from services.gateway.handlers import UnifiedMessageHandler
    
    assert MessageRouter is not None
    assert ServiceInstance is not None
    assert PriorityMessageQueue is not None
    assert MessagePriority is not None
    assert MessageDispatcher is not None
    assert UnifiedMessageHandler is not None


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])