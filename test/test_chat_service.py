"""
聊天服务测试模块
Chat Service Tests

作者: lx
日期: 2025-06-18
描述: 聊天服务相关功能的单元测试
"""
import pytest
import asyncio
import time
from datetime import datetime

from services.chat.models import ChatMessage, ChatType, MessageStatus, ChannelInfo
from services.chat.filters.word_filter import WordFilter, ACAutomaton


class TestChatModels:
    """聊天模型测试"""
    
    def test_chat_message_creation(self):
        """测试聊天消息创建"""
        message = ChatMessage(
            message_id="test_123",
            chat_type=ChatType.WORLD,
            channel="world",
            sender_id="player1",
            sender_name="TestPlayer",
            content="Hello World!",
            timestamp=time.time()
        )
        
        assert message.message_id == "test_123"
        assert message.chat_type == ChatType.WORLD
        assert message.channel == "world"
        assert message.sender_id == "player1"
        assert message.content == "Hello World!"
    
    def test_chat_message_serialization(self):
        """测试聊天消息序列化"""
        message = ChatMessage(
            message_id="test_456",
            chat_type=ChatType.PRIVATE,
            channel="private",
            sender_id="player1",
            sender_name="TestPlayer",
            receiver_id="player2",
            receiver_name="TargetPlayer",
            content="Private message",
            timestamp=time.time(),
            created_at=datetime.now()
        )
        
        # 测试JSON序列化
        json_str = message.to_json()
        assert isinstance(json_str, str)
        assert "test_456" in json_str
        
        # 测试反序列化
        restored_message = ChatMessage.from_json(json_str)
        assert restored_message.message_id == message.message_id
        assert restored_message.chat_type == message.chat_type
        assert restored_message.content == message.content
    
    def test_channel_info_creation(self):
        """测试频道信息创建"""
        channel = ChannelInfo(
            channel_id="channel_123",
            channel_name="测试频道",
            channel_type=ChatType.CHANNEL,
            creator_id="admin",
            description="这是一个测试频道"
        )
        
        assert channel.channel_id == "channel_123"
        assert channel.channel_name == "测试频道"
        assert channel.creator_id == "admin"
        assert channel.member_count == 0
        assert channel.is_active is True


class TestWordFilter:
    """敏感词过滤器测试"""
    
    def test_ac_automaton_basic(self):
        """测试AC自动机基础功能"""
        automaton = ACAutomaton()
        
        # 添加敏感词
        automaton.add_word("测试")
        automaton.add_word("敏感词")
        automaton.add_word("禁止")
        
        # 搜索文本
        text = "这是一个测试文本，包含敏感词和禁止内容"
        matches = automaton.search(text)
        
        # 验证匹配结果
        assert len(matches) == 3
        found_words = [word for _, word in matches]
        assert "测试" in found_words
        assert "敏感词" in found_words
        assert "禁止" in found_words
    
    def test_word_filter_initialization(self):
        """测试敏感词过滤器初始化"""
        # 使用默认敏感词
        from services.chat.filters.word_filter import get_word_filter
        word_filter = get_word_filter()
        stats = word_filter.get_statistics()
        
        assert stats["total_words"] > 0
        assert stats["categories"] >= 1
    
    def test_word_filter_basic_filtering(self):
        """测试基础过滤功能"""
        word_filter = WordFilter(["测试", "禁止", "屏蔽"])
        
        # 测试包含敏感词的文本
        text = "这个测试消息包含禁止内容"
        filtered_text, detected_words = word_filter.filter_text(text)
        
        assert len(detected_words) == 2
        assert "测试" in detected_words
        assert "禁止" in detected_words
        assert "*" in filtered_text  # 应该包含替换字符
    
    def test_word_filter_no_sensitive_words(self):
        """测试不包含敏感词的文本"""
        word_filter = WordFilter(["测试", "禁止"])
        
        text = "这是一个正常的消息内容"
        filtered_text, detected_words = word_filter.filter_text(text)
        
        assert len(detected_words) == 0
        assert filtered_text == text  # 应该不变
    
    def test_word_filter_add_remove_words(self):
        """测试添加和删除敏感词"""
        word_filter = WordFilter()
        
        # 添加敏感词
        word_filter.add_word("新敏感词", "test")
        assert word_filter.contains_sensitive_word("这包含新敏感词")
        
        # 删除敏感词
        success = word_filter.remove_word("新敏感词", "test")
        assert success is True
        assert not word_filter.contains_sensitive_word("这包含新敏感词")
    
    def test_word_filter_case_insensitive(self):
        """测试大小写不敏感"""
        word_filter = WordFilter(["Test", "BLOCK"])
        
        text = "This has test and block words"
        filtered_text, detected_words = word_filter.filter_text(text)
        
        assert "test" in detected_words
        assert "block" in detected_words
    
    def test_word_filter_overlapping_matches(self):
        """测试重叠匹配处理"""
        word_filter = WordFilter(["测试", "试验", "测试验证"])
        
        text = "进行测试验证工作"
        filtered_text, detected_words = word_filter.filter_text(text)
        
        # 应该匹配最长的词
        assert "测试验证" in detected_words
        # 不应该同时匹配短词
        assert len([w for w in detected_words if w in ["测试", "试验"]]) == 0


class TestChatMessageFlow:
    """聊天消息流程测试"""
    
    def test_message_validation(self):
        """测试消息验证"""
        # 测试正常消息
        message = ChatMessage(
            message_id="msg_001",
            chat_type=ChatType.WORLD,
            channel="world",
            sender_id="player1",
            sender_name="Player1",
            content="Hello everyone!",
            timestamp=time.time()
        )
        
        assert message.chat_type == ChatType.WORLD
        assert len(message.content) > 0
        
    def test_private_message_validation(self):
        """测试私聊消息验证"""
        message = ChatMessage(
            message_id="msg_002",
            chat_type=ChatType.PRIVATE,
            channel="private",
            sender_id="player1",
            sender_name="Player1",
            receiver_id="player2",
            receiver_name="Player2", 
            content="Private hello!",
            timestamp=time.time()
        )
        
        assert message.chat_type == ChatType.PRIVATE
        assert message.receiver_id is not None
        assert message.receiver_name is not None
    
    def test_message_status_flow(self):
        """测试消息状态流转"""
        message = ChatMessage(
            message_id="msg_003",
            chat_type=ChatType.WORLD,
            channel="world",
            sender_id="player1",
            sender_name="Player1",
            content="Status test",
            timestamp=time.time(),
            status=MessageStatus.PENDING
        )
        
        # 初始状态应该是PENDING
        assert message.status == MessageStatus.PENDING
        
        # 修改状态
        message.status = MessageStatus.SENT
        assert message.status == MessageStatus.SENT


@pytest.mark.asyncio
class TestAsyncChatComponents:
    """异步聊天组件测试"""
    
    async def test_word_filter_file_operations(self):
        """测试敏感词文件操作"""
        word_filter = WordFilter()
        
        # 测试统计信息
        stats = word_filter.get_statistics()
        assert isinstance(stats, dict)
        assert "total_words" in stats
        
    async def test_message_serialization_performance(self):
        """测试消息序列化性能"""
        messages = []
        
        # 创建大量消息
        for i in range(1000):
            message = ChatMessage(
                message_id=f"msg_{i}",
                chat_type=ChatType.WORLD,
                channel="world",
                sender_id=f"player_{i % 100}",
                sender_name=f"Player{i % 100}",
                content=f"Test message {i}",
                timestamp=time.time()
            )
            messages.append(message)
        
        # 测试序列化速度
        start_time = time.time()
        for message in messages:
            json_str = message.to_json()
            restored = ChatMessage.from_json(json_str)
            assert restored.message_id == message.message_id
        
        elapsed = time.time() - start_time
        assert elapsed < 5.0  # 应该在5秒内完成
        
        print(f"序列化1000条消息耗时: {elapsed:.3f}秒")


if __name__ == "__main__":
    # 运行特定的测试
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "basic":
        # 运行基础测试
        test_models = TestChatModels()
        test_models.test_chat_message_creation()
        test_models.test_chat_message_serialization()
        test_models.test_channel_info_creation()
        
        test_filter = TestWordFilter()
        test_filter.test_word_filter_initialization()
        test_filter.test_word_filter_basic_filtering()
        test_filter.test_word_filter_no_sensitive_words()
        
        print("✅ 基础测试通过")
    else:
        print("使用 'python test_chat_service.py basic' 运行基础测试")
        print("或使用 'pytest test_chat_service.py -v' 运行完整测试")