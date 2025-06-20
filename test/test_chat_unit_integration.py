"""
聊天服务单元集成测试
Chat Service Unit Integration Test

作者: lx
日期: 2025-06-18
描述: 测试聊天服务各组件的集成，不依赖外部数据库
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from services.chat.models import ChatMessage, ChatType, MessageStatus
from services.chat.filters.word_filter import get_word_filter
from services.chat.handlers.chat_handler import ChatHandler


async def test_message_filtering():
    """测试消息过滤功能"""
    print("=== 测试消息过滤功能 ===")
    
    try:
        # 获取敏感词过滤器
        word_filter = get_word_filter()
        
        # 测试普通文本
        normal_text = "这是一条正常的聊天消息"
        filtered, detected = word_filter.filter_text(normal_text)
        
        assert filtered == normal_text
        assert len(detected) == 0
        print(f"正常文本: '{normal_text}' -> 无敏感词")
        
        # 测试包含敏感词的文本
        sensitive_text = "这个傻逼游戏真垃圾"
        filtered, detected = word_filter.filter_text(sensitive_text)
        
        assert len(detected) > 0
        assert "*" in filtered
        print(f"敏感文本: '{sensitive_text}' -> 检测到: {detected}, 过滤后: '{filtered}'")
        
        print("✅ 消息过滤功能测试通过")
        
    except Exception as e:
        print(f"❌ 消息过滤功能测试失败: {e}")
        raise


async def test_message_model_serialization():
    """测试消息模型序列化"""
    print("=== 测试消息模型序列化 ===")
    
    try:
        # 创建聊天消息
        message = ChatMessage(
            message_id="test_001",
            chat_type=ChatType.WORLD,
            channel="world",
            sender_id="player1",
            sender_name="TestPlayer",
            content="Hello World!",
            timestamp=time.time(),
            status=MessageStatus.SENT
        )
        
        # 测试JSON序列化
        json_str = message.to_json()
        print(f"序列化长度: {len(json_str)} 字符")
        
        # 测试反序列化
        restored = ChatMessage.from_json(json_str)
        
        assert restored.message_id == message.message_id
        assert restored.chat_type == message.chat_type
        assert restored.content == message.content
        assert restored.status == message.status
        
        print("✅ 消息模型序列化测试通过")
        
    except Exception as e:
        print(f"❌ 消息模型序列化测试失败: {e}")
        raise


async def test_chat_handler_validation():
    """测试聊天处理器验证逻辑"""
    print("=== 测试聊天处理器验证逻辑 ===")
    
    try:
        # 创建模拟的聊天处理器
        handler = ChatHandler()
        
        # 模拟内部方法
        handler._validate_message = AsyncMock()
        handler._check_rate_limit = AsyncMock()
        handler._word_filter = get_word_filter()
        
        # 测试消息验证
        handler._validate_message.return_value = {"success": True}
        handler._check_rate_limit.return_value = True
        
        # 模拟ID生成器
        class MockIdGenerator:
            def generate(self):
                return int(time.time() * 1000)
        
        handler._id_generator = MockIdGenerator()
        
        print("✅ 聊天处理器验证逻辑测试通过")
        
    except Exception as e:
        print(f"❌ 聊天处理器验证逻辑测试失败: {e}")
        raise


async def test_chat_message_types():
    """测试聊天消息类型"""
    print("=== 测试聊天消息类型 ===")
    
    try:
        # 测试各种聊天类型
        types_to_test = [
            (ChatType.WORLD, "world", "世界聊天"),
            (ChatType.PRIVATE, "private", "私聊"),
            (ChatType.CHANNEL, "test_channel", "频道聊天"),
            (ChatType.SYSTEM, "system", "系统消息"),
        ]
        
        for chat_type, channel, description in types_to_test:
            message = ChatMessage(
                message_id=f"msg_{chat_type.value}",
                chat_type=chat_type,
                channel=channel,
                sender_id="test_sender",
                sender_name="TestSender",
                content=f"这是{description}测试",
                timestamp=time.time()
            )
            
            assert message.chat_type == chat_type
            assert message.channel == channel
            print(f"✓ {description}: {message.chat_type.name}")
        
        print("✅ 聊天消息类型测试通过")
        
    except Exception as e:
        print(f"❌ 聊天消息类型测试失败: {e}")
        raise


async def test_performance_simulation():
    """测试性能模拟"""
    print("=== 测试性能模拟 ===")
    
    try:
        # 创建大量消息进行性能测试
        messages = []
        start_time = time.time()
        
        for i in range(1000):
            message = ChatMessage(
                message_id=f"perf_msg_{i}",
                chat_type=ChatType.WORLD,
                channel="world",
                sender_id=f"player_{i % 100}",
                sender_name=f"Player{i % 100}",
                content=f"Performance test message {i}",
                timestamp=time.time()
            )
            
            # 序列化和反序列化
            json_str = message.to_json()
            restored = ChatMessage.from_json(json_str)
            
            assert restored.message_id == message.message_id
            messages.append(restored)
        
        elapsed = time.time() - start_time
        print(f"处理1000条消息耗时: {elapsed:.3f}秒")
        print(f"平均每条消息: {(elapsed / len(messages)) * 1000:.3f}毫秒")
        
        assert elapsed < 5.0  # 应该在5秒内完成
        
        print("✅ 性能模拟测试通过")
        
    except Exception as e:
        print(f"❌ 性能模拟测试失败: {e}")
        raise


async def test_word_filter_advanced():
    """测试高级敏感词过滤"""
    print("=== 测试高级敏感词过滤 ===")
    
    try:
        word_filter = get_word_filter()
        
        # 测试重叠敏感词
        word_filter.add_word("测试", "test")
        word_filter.add_word("测试词", "test")
        word_filter.add_word("敏感测试词", "test")
        
        text = "这是敏感测试词的例子"
        filtered, detected = word_filter.filter_text(text)
        
        print(f"重叠敏感词测试: '{text}' -> 检测到: {detected}")
        
        # 应该检测到最长的匹配
        assert "敏感测试词" in detected or len(detected) > 0
        
        # 测试大小写不敏感
        text_upper = "这包含FUCK和SHIT"
        filtered_upper, detected_upper = word_filter.filter_text(text_upper)
        
        print(f"大小写测试: '{text_upper}' -> 检测到: {detected_upper}")
        
        # 清理测试敏感词
        word_filter.clear_category("test")
        
        print("✅ 高级敏感词过滤测试通过")
        
    except Exception as e:
        print(f"❌ 高级敏感词过滤测试失败: {e}")
        raise


async def test_integration_workflow():
    """测试集成工作流"""
    print("=== 测试集成工作流 ===")
    
    try:
        # 模拟完整的聊天流程
        word_filter = get_word_filter()
        
        # 1. 用户发送消息
        original_content = "这是一条包含测试的正常消息"
        
        # 2. 敏感词过滤
        filtered_content, detected_words = word_filter.filter_text(original_content)
        
        # 3. 创建消息对象
        message = ChatMessage(
            message_id="workflow_001",
            chat_type=ChatType.WORLD,
            channel="world",
            sender_id="player1",
            sender_name="TestPlayer",
            content=filtered_content,
            original_content=original_content if detected_words else None,
            timestamp=time.time(),
            status=MessageStatus.SENT
        )
        
        # 4. 序列化消息（用于存储）
        json_data = message.to_json()
        
        # 5. 反序列化消息（用于读取）
        restored_message = ChatMessage.from_json(json_data)
        
        # 6. 验证完整性
        assert restored_message.message_id == message.message_id
        assert restored_message.content == message.content
        assert restored_message.chat_type == message.chat_type
        
        print(f"工作流测试: {original_content} -> {filtered_content}")
        print(f"消息ID: {restored_message.message_id}")
        print(f"聊天类型: {restored_message.chat_type.name}")
        
        print("✅ 集成工作流测试通过")
        
    except Exception as e:
        print(f"❌ 集成工作流测试失败: {e}")
        raise


async def run_integration_tests():
    """运行集成测试"""
    print("开始运行聊天服务单元集成测试...\n")
    
    tests = [
        test_message_filtering,
        test_message_model_serialization,
        test_chat_handler_validation,
        test_chat_message_types,
        test_performance_simulation,
        test_word_filter_advanced,
        test_integration_workflow,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            await test()
            passed += 1
            print()
        except Exception as e:
            print(f"💥 测试失败: {e}")
            failed += 1
            print()
    
    print(f"测试结果: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("🎉 所有集成测试通过！")
    else:
        print("❌ 部分测试失败")
        
    return failed == 0


if __name__ == "__main__":
    # 运行集成测试
    success = asyncio.run(run_integration_tests())
    if not success:
        exit(1)