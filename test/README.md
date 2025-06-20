# 测试框架使用说明
# Testing Framework Guide

## 概述 Overview

本测试框架为knight_hero_server游戏服务器提供全面的测试支持，包括单元测试、集成测试、压力测试等多种测试类型。

This testing framework provides comprehensive testing support for the knight_hero_server game server, including unit tests, integration tests, load tests, and more.

## 项目结构 Project Structure

```
test/
├── conftest.py                 # pytest配置和共享fixtures
├── unit/                       # 单元测试
│   ├── __init__.py
│   └── test_protocol.py       # 协议层单元测试
├── integration/               # 集成测试
│   ├── __init__.py
│   └── test_gateway.py       # 网关集成测试
├── load/                      # 压力测试
│   ├── __init__.py
│   └── locustfile.py         # Locust压力测试
├── utils/                     # 测试工具
│   ├── __init__.py
│   └── mock_client.py        # Mock客户端工具
└── run_tests.py              # 测试运行器
```

## 安装依赖 Dependencies

```bash
# 基础测试依赖
pip install pytest pytest-asyncio

# 压力测试依赖
pip install locust websocket-client

# 协议测试依赖
pip install lz4 cryptography websockets msgpack

# 其他依赖
pip install motor redis fastapi
```

## 测试运行 Running Tests

### 使用测试运行器 Using Test Runner

```bash
# 运行所有测试
python run_tests.py all

# 运行单元测试
python run_tests.py unit

# 运行集成测试  
python run_tests.py integration

# 运行协议测试
python run_tests.py protocol

# 运行网关测试
python run_tests.py gateway

# 运行Mock客户端测试
python run_tests.py mock
```

### 直接使用pytest Running with pytest directly

```bash
# 运行所有测试
pytest test/ -v

# 运行特定测试文件
pytest test/unit/test_protocol.py -v

# 运行特定测试类
pytest test/unit/test_protocol.py::TestProtocolEncoding -v

# 运行特定测试方法
pytest test/unit/test_protocol.py::TestProtocolEncoding::test_message_header_encoding -v

# 运行异步测试
pytest test/integration/test_gateway.py -v --asyncio-mode=auto
```

## 压力测试 Load Testing

### 使用Locust进行压力测试

```bash
# 启动Locust Web界面 (需要服务器运行在localhost:8000)
locust -f test/load/locustfile.py --host=http://localhost:8000

# 命令行模式运行压力测试
locust -f test/load/locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 60s --headless

# 模拟10K用户压力测试
locust -f test/load/locustfile.py --host=http://localhost:8000 --users 10000 --spawn-rate 100 --run-time 300s --headless
```

### Locust测试场景 Test Scenarios

- **登录测试**: 用户登录流程测试
- **聊天测试**: 高频聊天消息发送
- **玩家信息查询**: 中频数据查询操作
- **战斗系统**: 低频重计算操作
- **位置移动**: 实时位置更新
- **道具使用**: 游戏内物品使用

## Mock客户端工具 Mock Client Tools

### 基本使用 Basic Usage

```python
from test.utils.mock_client import MockWebSocketClient, MessageBuilder, BatchTestRunner

# 创建单个客户端
client = MockWebSocketClient("ws://localhost:8000/ws")
await client.connect()

# 发送登录消息
login_msg = MessageBuilder.create_login_message("user123", "player123")
result = await client.send_and_wait_response(login_msg)

# 批量测试
runner = BatchTestRunner("ws://localhost:8000/ws", max_concurrent=50)
stats = await runner.run_batch_test(100, TestScenarios.simple_login_test)
```

### 测试场景 Test Scenarios

- `simple_login_test`: 简单登录测试
- `chat_flood_test`: 聊天消息洪水测试  
- `comprehensive_test`: 综合功能测试
- `stress_test`: 压力测试场景

## 测试配置 Test Configuration

### conftest.py配置项

- **Mock Services**: Redis、MongoDB、WebSocket的模拟实现
- **Test Fixtures**: 共享的测试数据和对象
- **Performance Helpers**: 性能测量工具
- **Data Generators**: 测试数据生成器

### 环境变量 Environment Variables

```bash
export TEST_DATABASE_URL="mock://test_database"
export TEST_REDIS_URL="mock://test_redis"
export TEST_HOST="127.0.0.1"
export TEST_PORT="8888"
```

## 测试类型说明 Test Types

### 1. 单元测试 Unit Tests

- **协议编解码测试**: 消息头/体编码、压缩、加密
- **消息序列化测试**: JSON/MessagePack序列化性能  
- **加密解密测试**: AES加密、密钥派生、完整性验证
- **错误处理测试**: 异常情况和边界条件
- **性能测试**: 吞吐量和并发处理能力

### 2. 集成测试 Integration Tests

- **WebSocket连接测试**: 连接创建、消息收发、生命周期
- **消息路由测试**: 处理器注册、消息分发、路由性能
- **会话管理测试**: 会话创建、认证、清理、并发操作
- **网关集成测试**: 完整消息流、错误处理、性能验证

### 3. 压力测试 Load Tests

- **并发连接测试**: 10K并发WebSocket连接
- **消息吞吐量测试**: 高频消息处理能力
- **业务场景测试**: 真实游戏场景模拟
- **性能监控**: 响应时间、错误率、资源使用

## 性能基准 Performance Benchmarks

### 协议层性能要求

- 消息编解码: < 1ms per message
- 批量处理: > 10K messages/sec
- 加密解密: < 0.5ms per message
- 并发处理: 支持1000+并发

### 网关层性能要求

- WebSocket连接: 100个并发连接 < 1秒
- 消息路由: < 1ms per message
- 会话管理: > 1K sessions/sec
- 错误率: < 1%

### 压力测试目标

- 并发用户: 10,000 users
- 消息吞吐量: > 100K messages/sec  
- 响应时间: P95 < 100ms
- 系统稳定性: 5分钟压测无崩溃

## 测试报告 Test Reports

### 单元测试报告

```
pytest test/unit/ --cov=common --cov-report=html
```

### 压力测试报告

Locust自动生成HTML报告，包含:
- 请求统计
- 响应时间分布
- 错误率分析
- 并发用户图表

### Mock客户端报告

```python
stats = await runner.run_batch_test(100, scenario)
print_batch_stats(stats)
```

包含详细的:
- 客户端成功率
- 消息统计
- 响应时间分析
- 错误分类

## 最佳实践 Best Practices

### 测试编写建议

1. **独立性**: 每个测试应该独立运行
2. **可重复性**: 测试结果应该一致
3. **快速性**: 单元测试应该快速完成
4. **覆盖性**: 覆盖主要功能和边界情况
5. **可读性**: 测试代码应该清晰易懂

### 性能测试建议

1. **渐进式**: 逐步增加负载
2. **监控**: 监控系统资源使用
3. **基准**: 建立性能基准线
4. **分析**: 深入分析性能瓶颈
5. **优化**: 基于测试结果优化代码

### Mock使用建议

1. **轻量级**: Mock应该简单快速
2. **行为一致**: Mock行为应该与真实服务一致
3. **数据隔离**: 测试数据应该隔离
4. **状态管理**: 正确管理Mock状态
5. **清理**: 测试后清理Mock数据

## 故障排除 Troubleshooting

### 常见问题

1. **依赖缺失**: 确保安装所有必需的Python包
2. **端口冲突**: 检查测试端口是否被占用
3. **异步问题**: 确保正确使用pytest-asyncio
4. **Mock数据**: 检查Mock数据是否正确设置
5. **超时问题**: 调整测试超时设置

### 调试技巧

```bash
# 详细输出
pytest -v -s

# 停在第一个失败
pytest -x

# 显示本地变量
pytest -l

# 调试模式
pytest --pdb
```

## 贡献指南 Contributing

### 添加新测试

1. 在对应目录创建测试文件
2. 使用合适的测试类和方法命名
3. 添加详细的中文注释
4. 确保测试通过
5. 更新文档

### 测试命名规范

- 测试文件: `test_*.py`
- 测试类: `Test*`
- 测试方法: `test_*`
- 异步测试: 使用`@pytest.mark.asyncio`

## 联系方式 Contact

如有问题或建议，请联系开发团队。

For questions or suggestions, please contact the development team.