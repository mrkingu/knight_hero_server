# 异步日志系统文档
# Async Logger System Documentation

## 概述 (Overview)

本项目实现了一个高性能的异步日志系统，满足以下技术要求：

- 基于 asyncio 的异步日志记录
- 批量写入优化（100条记录或1秒触发）
- 支持日志分类（玩家、战斗、系统、错误）
- 文件自动轮转和清理
- 队列缓冲机制（10000条容量）

## 核心特性 (Core Features)

### 1. 异步架构
- **AsyncLogger**: 核心异步日志器类
- **队列缓冲**: 使用 asyncio.Queue 进行异步缓冲
- **批量处理**: 批量写入提高性能
- **并发安全**: 支持多协程并发日志记录

### 2. 文件处理器
- **AsyncFileHandler**: 基础异步文件写入
- **AsyncRotatingFileHandler**: 按大小轮转（默认100MB）
- **AsyncTimedRotatingFileHandler**: 按时间轮转（支持每日、每小时等）
- **自动压缩**: 旧日志文件自动压缩为 .gz 格式
- **自动清理**: 保留指定数量的备份文件

### 3. 格式化器
- **JSONFormatter**: JSON格式日志，支持结构化数据
- **SimpleFormatter**: 简单文本格式，便于阅读
- **ColoredFormatter**: 彩色控制台输出

### 4. 预配置日志器
- **player_logger**: 玩家操作日志
- **battle_logger**: 战斗事件日志
- **system_logger**: 系统事件日志
- **error_logger**: 错误日志
- **debug_logger**: 调试日志

## 使用方法 (Usage)

### 基本使用

```python
import asyncio
from common.logger import initialize_loggers, get_player_logger, shutdown_loggers

async def main():
    # 初始化日志系统
    await initialize_loggers("production")  # 或 "development"
    
    try:
        # 获取日志器
        player_logger = await get_player_logger()
        
        # 记录日志
        await player_logger.info(
            "用户登录",
            player_id="player_123",
            ip="192.168.1.1",
            device="iPhone"
        )
        
    finally:
        # 关闭日志系统
        await shutdown_loggers()

asyncio.run(main())
```

### 便捷函数

```python
from common.logger import log_player_action, log_battle_event

# 记录玩家操作
await log_player_action(
    "购买道具",
    player_id="player_123",
    item_id="sword",
    cost=100
)

# 记录战斗事件
await log_battle_event(
    "技能释放",
    battle_id="battle_456",
    player_id="player_123",
    skill_id="fireball",
    damage=150
)
```

### 自定义日志器

```python
from common.logger import get_logger

# 获取自定义日志器
custom_logger = await get_logger("my_module")

await custom_logger.info("模块初始化完成", version="1.0.0")
```

## 配置说明 (Configuration)

### 环境配置

系统支持两种环境配置：

- **production**: 生产环境，日志输出到文件，包含完整的轮转和压缩
- **development**: 开发环境，主要输出到控制台，便于调试

### 日志级别

支持标准的 Python 日志级别：
- `DEBUG`: 调试信息
- `INFO`: 一般信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息
- `CRITICAL`: 严重错误

### 文件配置

默认日志文件存储在 `logs/` 目录下：

- `logs/player.log` - 玩家操作日志
- `logs/battle.log` - 战斗事件日志
- `logs/system.log` - 系统事件日志
- `logs/error.log` - 错误日志
- `logs/debug.log` - 调试日志

### 轮转配置

- **按大小轮转**: 文件达到100MB时自动轮转
- **按时间轮转**: 每日午夜自动轮转
- **备份数量**: 保留10个备份文件（可配置）
- **自动压缩**: 旧文件自动压缩为 .gz 格式

## 性能指标 (Performance)

### 基准测试结果

- **吞吐量**: > 4000 条日志/秒
- **内存使用**: 队列缓冲 10000 条记录
- **批量处理**: 100 条记录或 1 秒触发批量写入
- **并发支持**: 支持多协程并发写入

### 内存管理

- 队列满时自动丢弃新日志并记录统计
- 异步文件操作避免阻塞主线程
- 自动清理过期日志文件

## API 参考 (API Reference)

### 核心函数

#### `initialize_loggers(environment: str = "production")`
初始化日志系统
- `environment`: "production" 或 "development"

#### `get_logger(name: str) -> AsyncLogger`
获取指定名称的日志器

#### `shutdown_loggers()`
关闭所有日志器并清理资源

### 预配置日志器

#### `get_player_logger() -> AsyncLogger`
获取玩家日志器

#### `get_battle_logger() -> AsyncLogger`
获取战斗日志器

#### `get_system_logger() -> AsyncLogger`
获取系统日志器

#### `get_error_logger() -> AsyncLogger`
获取错误日志器

### 便捷函数

#### `log_player_action(action: str, player_id: str, **extra_data)`
记录玩家操作日志

#### `log_battle_event(event: str, battle_id: str, **extra_data)`
记录战斗事件日志

#### `log_system_event(event: str, component: str, **extra_data)`
记录系统事件日志

#### `log_error(error: str, error_type: str = "Unknown", **extra_data)`
记录错误日志

### 统计信息

#### `get_logger_stats() -> Dict`
获取所有日志器的统计信息，包括：
- `total_logs`: 总日志数
- `dropped_logs`: 丢弃的日志数
- `batch_count`: 批次处理次数
- `queue_size`: 当前队列大小
- `is_running`: 是否正在运行

## 最佳实践 (Best Practices)

### 1. 错误处理
```python
try:
    result = await some_operation()
    await log_player_action("操作成功", player_id, result=result)
except Exception as e:
    await log_error(f"操作失败: {e}", "OperationError", player_id=player_id)
```

### 2. 结构化日志
```python
await player_logger.info(
    "用户购买道具",
    player_id="123",
    item_id="sword",
    item_type="weapon",
    cost=100,
    currency="gold",
    timestamp=time.time()
)
```

### 3. 性能优化
- 避免在日志消息中执行重计算
- 使用适当的日志级别
- 合理设置批量大小和超时时间

### 4. 监控和告警
```python
# 定期检查日志系统状态
stats = get_logger_stats()
for logger_name, stat in stats.items():
    if stat["dropped_logs"] > 0:
        await log_error(f"日志器 {logger_name} 丢失日志", "LoggingError")
```

## 故障排除 (Troubleshooting)

### 常见问题

1. **日志文件未生成**
   - 检查 `logs/` 目录权限
   - 确认日志器已正确初始化

2. **性能问题**
   - 检查队列是否经常满载
   - 调整批量大小和超时参数
   - 监控磁盘I/O性能

3. **内存使用过高**
   - 减少队列大小
   - 增加批量处理频率
   - 检查是否有日志器未正确关闭

### 调试模式

在开发环境中启用调试模式：
```python
await initialize_loggers("development")
```

这将：
- 启用DEBUG级别日志
- 主要输出到控制台
- 显示详细的错误信息

## 扩展开发 (Extension Development)

### 自定义格式化器

```python
from common.logger.formatters import JSONFormatter

class CustomFormatter(JSONFormatter):
    def format(self, record):
        # 自定义格式化逻辑
        return super().format(record)
```

### 自定义处理器

```python
from common.logger.handlers import AsyncFileHandler

class CustomHandler(AsyncFileHandler):
    async def emit_async(self, record):
        # 自定义处理逻辑
        await super().emit_async(record)
```

### 自定义配置

```python
from common.logger.config import LOG_CONFIG

# 修改配置
LOG_CONFIG["custom"] = {
    "level": "INFO",
    "handlers": [
        {
            "type": "file",
            "filename": "logs/custom.log",
            "formatter": {"type": "json"}
        }
    ]
}
```

## 贡献指南 (Contributing)

### 代码规范
- 遵循 PEP 8 编码规范
- 使用 Type Hints 进行类型标注
- 添加详细的中文注释
- 编写单元测试

### 测试
运行测试套件：
```bash
python -m pytest test/test_logger.py -v
```

### 性能测试
```bash
python test/test_logger.py  # 包含性能基准测试
```