# 游戏服务器框架快速开始指南

**版本**: 2.0  
**更新日期**: 2025-06-20  
**作者**: mrkingu

## 概述

本框架提供了开箱即用的游戏服务器基础设施，开发者只需关注业务逻辑，无需关心底层实现。

## 核心特性

### 🚀 开发效率提升
- **脚手架生成器**: 一键生成标准化代码模板
- **依赖注入**: 自动装载和管理服务依赖
- **统一架构**: 标准化的Handler/Service/Repository分层

### ⚡ 性能优化
- **智能缓存**: 多级缓存机制，自动过期清理
- **批量处理**: 批量操作优化，减少数据库访问
- **对象池**: 减少对象创建开销
- **性能监控**: 自动收集和分析性能指标

### 🛡️ 稳定可靠
- **统一异常处理**: 标准化错误码和异常体系
- **健康检查**: 实时监控服务状态
- **熔断器**: 防止服务雪崩
- **限流控制**: 保护系统资源

## 快速开始

### 1. 创建新的业务模块

使用脚手架生成器创建完整的业务模块：

```bash
# 生成完整模块（包含Service、Handler、Repository、Model）
python scripts/scaffold_generator.py generate-module --name Item --module logic

# 或者单独生成组件
python scripts/scaffold_generator.py generate --type service --name Item --module logic
python scripts/scaffold_generator.py generate --type handler --name Item --module logic
python scripts/scaffold_generator.py generate --type repository --name Item --module logic
python scripts/scaffold_generator.py generate --type model --name Item
```

生成的文件结构：
```
services/logic/
├── services/item_service.py       # 业务服务
├── handlers/item_handler.py       # 请求处理器
└── repositories/item_repository.py # 数据仓库
common/models/item_model.py         # 数据模型
```

### 2. 实现业务逻辑

#### 2.1 Service层（业务逻辑）
```python
from common.ioc import service, autowired
from common.base import BaseGameService
from common.exceptions import ValidationError, ItemNotFoundError
from common.performance import async_cached, monitor_performance

@service("ItemService")
class ItemService(BaseGameService):
    
    @autowired("ItemRepository")
    def repository(self):
        pass
    
    @monitor_performance("item_create")
    async def create_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # 1. 参数验证
        self.validate_params(data, ["name", "type"])
        
        # 2. 业务逻辑
        item_data = {
            "name": data["name"],
            "type": data["type"],
            "player_id": data.get("player_id")
        }
        
        # 3. 数据持久化
        result = await self.repository.create(item_data)
        
        # 4. 记录业务日志
        await self.log_business_action(
            data.get("player_id", "system"),
            "create_item",
            data,
            result
        )
        
        return self.success_response(result)
```

#### 2.2 Handler层（请求处理）
```python
from common.ioc import service, autowired
from common.base import DictHandler
from common.exceptions import ValidationError

@service("ItemHandler")  
class ItemHandler(DictHandler):
    
    @autowired("ItemService")
    def service(self):
        pass
    
    async def validate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        # 参数验证
        action = request.get("action")
        if not action:
            raise ValidationError("Missing action parameter")
        return request
    
    async def process(self, request: Dict[str, Any]) -> Any:
        # 业务处理分发
        action = request["action"]
        
        if action == "create":
            return await self.service.create_item(request)
        elif action == "get":
            return await self.service.get_item(request["item_id"])
        # ... 其他操作
```

### 3. 服务注册和启动

框架会自动扫描和注册服务：

```python
from common.ioc import ServiceContainer

# 启动服务容器
container = ServiceContainer()
await container.initialize([
    "services.logic",  # 扫描logic模块
    "services.chat",   # 扫描chat模块
])

# 获取服务实例
item_handler = container.get_service("ItemHandler")
result = await item_handler.handle({
    "action": "create",
    "name": "魔法剑",
    "type": "weapon"
})
```

## 核心功能使用

### 缓存使用

```python
from common.performance import async_cached

@async_cached(ttl=300)  # 缓存5分钟
async def get_player_info(self, player_id: str):
    return await self.repository.find_by_id(player_id)

# 或使用服务内置缓存
async def get_cached_data(self, key: str):
    data = await self.cache_get(key)
    if data is None:
        data = await self.load_data_from_db(key)
        await self.cache_set(key, data, ttl=300)
    return data
```

### 性能监控

```python
from common.performance import monitor_performance

@monitor_performance("database_query")
async def complex_query(self):
    # 复杂查询逻辑
    pass

# 手动记录指标
self.record_metric("user_login", 1.0, {"source": "mobile"})

# 获取性能统计
stats = self.get_performance_stats()
```

### 异常处理

```python
from common.exceptions import ValidationError, ItemNotFoundError, handle_exception

@handle_exception  # 自动处理异常
async def risky_operation(self):
    if not valid:
        raise ValidationError("Invalid parameters")
    
    if not found:
        raise ItemNotFoundError("item_123")
```

### 健康检查

```python
from common.health import health_service, DatabaseHealthChecker

# 注册健康检查器
health_service.register_checker(DatabaseHealthChecker(db_client))

# 执行健康检查
result = await health_service.check_all()
print(f"Overall status: {result['status']}")
```

## 开发工具

### 代码格式化
```bash
# 格式化代码
black . --line-length 100

# 排序导入
isort . --profile black

# 代码检查
pylint common/ services/ --max-line-length=100

# 类型检查
mypy common/ services/
```

### 测试
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest test/test_item_service.py -v

# 测试覆盖率
pytest --cov=common --cov=services
```

## 最佳实践

### 1. 服务设计原则
- **单一职责**: 每个服务只处理一个业务领域
- **无状态设计**: 服务实例不应保存请求状态
- **依赖注入**: 使用@autowired注入依赖，便于测试

### 2. 错误处理
- **使用标准异常**: 继承GameException创建业务异常
- **适当层级处理**: Handler处理格式转换，Service处理业务异常
- **记录详细日志**: 包含上下文信息便于排查

### 3. 性能优化
- **合理使用缓存**: 频繁访问的数据加缓存
- **批量操作**: 避免循环调用数据库
- **异步IO**: 所有IO操作都要异步

### 4. 监控告警
- **健康检查**: 为关键依赖添加健康检查
- **性能监控**: 关键操作添加监控指标
- **业务日志**: 重要操作记录业务日志

## 配置说明

### 服务配置
```python
# 在服务中获取配置
cache_ttl = self.get_config("cache_ttl", 300)
enable_metrics = self.get_config("enable_metrics", True)
```

### 全局配置文件
```yaml
# config/app.yaml
services:
  item_service:
    cache_ttl: 600
    enable_metrics: true
    max_cache_size: 2000
    
performance:
  monitoring_enabled: true
  metrics_interval: 30
  
health:
  check_interval: 30
  endpoints:
    - database
    - redis
    - external_api
```

## 部署指南

### 开发环境
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m services.logic.main

# 启动网关
python -m services.gateway.main
```

### 生产环境
```bash
# 使用supervisor管理进程
supervisorctl start game_logic
supervisorctl start game_gateway
supervisorctl start game_chat
supervisorctl start game_fight
```

## 故障排查

### 常见问题

1. **服务启动失败**
   - 检查依赖注入配置
   - 确认数据库连接
   - 查看日志输出

2. **性能问题** 
   - 查看性能监控指标
   - 检查缓存命中率
   - 分析慢查询日志

3. **内存泄漏**
   - 检查缓存大小限制
   - 确认对象池配置
   - 监控内存使用趋势

### 调试工具
```python
# 获取服务统计信息
stats = service.get_performance_stats()

# 获取健康检查结果
health = await health_service.get_last_results()

# 获取缓存统计
cache_stats = service.get_cache_stats()
```

## 扩展开发

### 自定义中间件
```python
class CustomMiddleware:
    async def before_process(self, request):
        # 前置处理
        pass
    
    async def after_process(self, response):
        # 后置处理
        pass
```

### 自定义健康检查器
```python
class CustomHealthChecker(HealthChecker):
    async def check(self) -> Dict[str, Any]:
        # 自定义检查逻辑
        return {
            "status": "healthy",
            "message": "Custom check passed"
        }
```

## 总结

本框架通过提供标准化的基础设施，让开发者能够：

- **快速开发**: 使用脚手架快速生成标准代码
- **专注业务**: 框架处理技术细节，专注业务逻辑
- **高性能**: 内置性能优化，无需手动调优
- **高可用**: 完善的监控和故障处理机制

通过遵循本指南，您可以快速构建高质量的游戏服务器应用。