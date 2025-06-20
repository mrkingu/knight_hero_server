"""
异步日志系统测试
Async Logger System Tests

作者: lx
日期: 2025-06-18
描述: 测试异步日志系统的各个组件
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from common.logger import (
    AsyncLogger, AsyncLoggerManager, initialize_loggers, get_logger,
    get_player_logger, log_player_action, get_logger_stats
)
from common.logger.formatters import JSONFormatter, SimpleFormatter, ColoredFormatter
from common.logger.handlers import (
    AsyncFileHandler, AsyncRotatingFileHandler, AsyncTimedRotatingFileHandler
)
from common.logger.async_logger import LogRecord


class TestFormatters:
    """测试格式化器"""
    
    def test_json_formatter(self):
        """测试JSON格式化器"""
        formatter = JSONFormatter()
        
        # 创建测试记录
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=123,
            msg="测试消息",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        record.custom_field = "custom_value"
        
        # 格式化
        result = formatter.format(record)
        data = json.loads(result)
        
        # 验证基本字段
        assert data["level"] == "INFO"
        assert data["logger"] == "test_logger"
        assert data["message"] == "测试消息"
        assert data["line"] == 123
        assert "timestamp" in data
        assert "extra" in data
        assert data["extra"]["custom_field"] == "custom_value"
    
    def test_simple_formatter(self):
        """测试简单格式化器"""
        formatter = SimpleFormatter()
        
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=123,
            msg="测试消息",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        record.custom_field = "custom_value"
        
        result = formatter.format(record)
        
        assert "INFO" in result
        assert "test_logger" in result
        assert "测试消息" in result
        assert "custom_field=custom_value" in result
    
    def test_colored_formatter(self):
        """测试彩色格式化器"""
        formatter = ColoredFormatter()
        
        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/test/path.py",
            lineno=123,
            msg="错误消息",
            args=(),
            exc_info=None
        )
        record.created = 1234567890.123
        
        result = formatter.format(record)
        
        # 应该包含ANSI颜色代码
        assert "\033[31m" in result  # 红色
        assert "\033[0m" in result   # 重置
        assert "错误消息" in result


@pytest.mark.asyncio
class TestAsyncHandlers:
    """测试异步处理器"""
    
    async def test_async_file_handler(self):
        """测试异步文件处理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            handler = AsyncFileHandler(log_file)
            handler.setFormatter(SimpleFormatter())
            
            # 创建测试记录
            record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="/test/path.py",
                lineno=123,
                msg="测试消息",
                args=(),
                exc_info=None
            )
            
            # 写入日志
            await handler.emit_async(record)
            await handler.close_async()
            
            # 验证文件内容
            assert log_file.exists()
            content = log_file.read_text(encoding='utf-8')
            assert "测试消息" in content
    
    async def test_async_rotating_file_handler(self):
        """测试按大小轮转的文件处理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            # 设置小的文件大小以触发轮转
            handler = AsyncRotatingFileHandler(
                log_file,
                max_bytes=100,  # 100字节
                backup_count=3
            )
            handler.setFormatter(SimpleFormatter())
            
            # 写入足够的日志以触发轮转
            for i in range(10):
                record = logging.LogRecord(
                    name="test_logger",
                    level=logging.INFO,
                    pathname="/test/path.py",
                    lineno=123,
                    msg=f"测试消息 {i} " + "x" * 50,  # 长消息
                    args=(),
                    exc_info=None
                )
                await handler.emit_async(record)
            
            await handler.close_async()
            
            # 应该有轮转文件
            assert log_file.exists()
            backup_files = list(Path(temp_dir).glob("test.log.*"))
            assert len(backup_files) > 0
    
    async def test_async_timed_rotating_file_handler(self):
        """测试按时间轮转的文件处理器"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            handler = AsyncTimedRotatingFileHandler(
                log_file,
                when='S',  # 按秒轮转
                interval=1,
                backup_count=2
            )
            handler.setFormatter(SimpleFormatter())
            
            # 写入日志
            record = logging.LogRecord(
                name="test_logger",
                level=logging.INFO,
                pathname="/test/path.py",
                lineno=123,
                msg="测试消息",
                args=(),
                exc_info=None
            )
            
            await handler.emit_async(record)
            
            # 等待足够时间触发轮转
            await asyncio.sleep(1.1)
            
            # 再写入一条日志
            await handler.emit_async(record)
            await handler.close_async()
            
            assert log_file.exists()


@pytest.mark.asyncio
class TestAsyncLogger:
    """测试异步日志器"""
    
    async def test_log_record_creation(self):
        """测试日志记录创建"""
        record = LogRecord(
            level=logging.INFO,
            message="测试消息",
            logger_name="test_logger",
            timestamp=time.time(),
            extra_data={"key": "value"}
        )
        
        logging_record = record.to_logging_record()
        
        assert logging_record.name == "test_logger"
        assert logging_record.levelno == logging.INFO
        assert logging_record.getMessage() == "测试消息"
        assert hasattr(logging_record, "key")
        assert getattr(logging_record, "key") == "value"
    
    async def test_async_logger_basic_operations(self):
        """测试异步日志器基本操作"""
        logger = AsyncLogger("test_logger", level=logging.DEBUG)
        await logger.start()
        
        try:
            # 测试各级别日志
            assert await logger.debug("调试消息")
            assert await logger.info("信息消息")
            assert await logger.warning("警告消息")
            assert await logger.error("错误消息")
            assert await logger.critical("严重错误消息")
            
            # 测试带额外数据的日志
            assert await logger.info("带数据的消息", user_id="123", action="login")
            
            # 等待批次处理
            await asyncio.sleep(0.1)
            
            # 检查统计
            stats = logger.get_stats()
            assert stats["total_logs"] > 0
            assert stats["is_running"] is True
            
        finally:
            await logger.stop()
    
    async def test_async_logger_batch_processing(self):
        """测试批量处理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "batch_test.log"
            
            handler = AsyncFileHandler(log_file)
            handler.setFormatter(SimpleFormatter())
            
            logger = AsyncLogger(
                "batch_test",
                batch_size=5,  # 小批次大小
                batch_timeout=0.5
            )
            logger.add_handler(handler)
            await logger.start()
            
            try:
                # 发送多条日志
                for i in range(10):
                    await logger.info(f"批次消息 {i}")
                
                # 等待批次处理
                await asyncio.sleep(1.0)
                
                stats = logger.get_stats()
                assert stats["batch_count"] >= 1
                
            finally:
                await logger.stop()
                await handler.close_async()
            
            # 验证文件内容
            if log_file.exists():
                content = log_file.read_text(encoding='utf-8')
                assert "批次消息 0" in content
                assert "批次消息 9" in content
    
    async def test_async_logger_queue_full(self):
        """测试队列满的情况"""
        logger = AsyncLogger(
            "queue_test",
            queue_size=5,  # 小队列
            batch_size=100,  # 大批次，防止自动处理
            batch_timeout=10.0
        )
        
        # 不启动工作器，让队列堆积
        
        # 填满队列
        for i in range(10):  # 超过队列大小
            result = await logger.info(f"消息 {i}")
            if i < 5:
                assert result is True  # 前5条应该成功
            else:
                assert result is False  # 后面的应该失败
        
        stats = logger.get_stats()
        assert stats["dropped_logs"] > 0
        assert stats["queue_full_count"] > 0


@pytest.mark.asyncio 
class TestAsyncLoggerManager:
    """测试异步日志器管理器"""
    
    async def test_logger_manager_basic(self):
        """测试日志器管理器基本功能"""
        manager = AsyncLoggerManager()
        
        try:
            # 获取日志器
            logger1 = await manager.get_logger("test1")
            logger2 = await manager.get_logger("test2")
            logger3 = await manager.get_logger("test1")  # 重复获取
            
            assert logger1 is not logger2
            assert logger1 is logger3  # 应该返回相同实例
            
            # 测试日志记录
            await logger1.info("测试消息1")
            await logger2.info("测试消息2")
            
            # 获取统计信息
            stats = manager.get_all_stats()
            assert "test1" in stats
            assert "test2" in stats
            
        finally:
            await manager.stop_all()
    
    async def test_logger_configuration(self):
        """测试日志器配置"""
        manager = AsyncLoggerManager()
        
        config = {
            "level": "DEBUG",
            "queue_size": 1000,
            "batch_size": 50,
            "handlers": [
                {
                    "type": "console",
                    "level": "INFO",
                    "formatter": {
                        "type": "simple",
                        "format": "[TEST] {message}"
                    }
                }
            ]
        }
        
        try:
            logger = await manager.configure_logger("config_test", config)
            
            assert logger.level == logging.DEBUG
            assert logger.queue_size == 1000
            assert logger.batch_size == 50
            assert len(logger.handlers) == 1
            
        finally:
            await manager.stop_all()


@pytest.mark.asyncio
class TestLoggerInterface:
    """测试日志器接口"""
    
    async def test_initialize_and_get_logger(self):
        """测试初始化和获取日志器"""
        # 使用开发环境配置进行测试
        await initialize_loggers("development")
        
        try:
            # 获取预配置的日志器
            player_logger = await get_player_logger()
            assert player_logger is not None
            assert player_logger.name == "player"
            
            # 测试日志记录
            result = await log_player_action(
                "用户登录",
                player_id="test_player_123",
                ip="127.0.0.1",
                device="test"
            )
            assert result is True
            
            # 获取统计信息
            stats = get_logger_stats()
            assert "player" in stats
            
        finally:
            from common.logger import shutdown_loggers
            await shutdown_loggers()
    
    async def test_custom_logger(self):
        """测试自定义日志器"""
        try:
            custom_logger = await get_logger("custom_test")
            assert custom_logger is not None
            assert custom_logger.name == "custom_test"
            
            await custom_logger.info("自定义日志消息", test_field="test_value")
            
            stats = custom_logger.get_stats()
            assert stats["total_logs"] > 0
            
        finally:
            from common.logger import shutdown_loggers
            await shutdown_loggers()


@pytest.mark.asyncio
class TestPerformance:
    """性能测试"""
    
    async def test_high_volume_logging(self):
        """测试高容量日志记录"""
        logger = AsyncLogger(
            "performance_test",
            queue_size=10000,
            batch_size=1000,
            batch_timeout=0.1
        )
        
        await logger.start()
        
        try:
            start_time = time.time()
            
            # 发送大量日志
            log_count = 5000
            tasks = []
            for i in range(log_count):
                tasks.append(logger.info(f"性能测试消息 {i}", index=i))
            
            results = await asyncio.gather(*tasks)
            success_count = sum(1 for r in results if r)
            
            # 等待处理完成
            await asyncio.sleep(1.0)
            
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"发送 {log_count} 条日志，成功 {success_count} 条，耗时 {duration:.2f} 秒")
            print(f"平均速度: {success_count/duration:.0f} 条/秒")
            
            # 验证性能要求
            assert success_count > log_count * 0.9  # 至少90%成功
            assert success_count / duration > 1000  # 至少1000条/秒
            
        finally:
            await logger.stop()


def test_import_and_basic_functionality():
    """测试基本导入和功能"""
    # 测试所有导入
    from common.logger import (
        AsyncLogger, JSONFormatter, SimpleFormatter,
        AsyncFileHandler, initialize_loggers
    )
    
    # 基本功能测试
    formatter = JSONFormatter()
    assert formatter is not None
    
    simple_formatter = SimpleFormatter()
    assert simple_formatter is not None


if __name__ == "__main__":
    # 运行基本测试
    test_import_and_basic_functionality()
    print("✅ 基本导入测试通过")
    
    # 运行异步测试
    async def run_async_tests():
        print("开始异步测试...")
        
        # 测试格式化器
        test_formatters = TestFormatters()
        test_formatters.test_json_formatter()
        test_formatters.test_simple_formatter()
        print("✅ 格式化器测试通过")
        
        # 测试异步日志器
        test_logger = TestAsyncLogger()
        await test_logger.test_async_logger_basic_operations()
        print("✅ 异步日志器基本操作测试通过")
        
        await test_logger.test_async_logger_batch_processing()
        print("✅ 批量处理测试通过")
        
        # 测试性能
        perf_test = TestPerformance()
        await perf_test.test_high_volume_logging()
        print("✅ 性能测试通过")
        
        print("🎉 所有测试通过！")
    
    asyncio.run(run_async_tests())