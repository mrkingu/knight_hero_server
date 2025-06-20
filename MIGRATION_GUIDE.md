# 代码重构迁移指南

## 概述

本次重构的目标是清理重复代码、优化gRPC装饰器、封装数据访问层，提高代码可维护性。

## 主要改动

### 1. 统一工具模块

**之前：**
```python
# 分散在各个文件中的序列化方法
from common.protocol.utils.serializer import serialize_msgpack
from services.chat.models import ChatMessage
message.to_json()
```

**现在：**
```python
# 统一的序列化接口
from common.utils import auto_serialize, auto_deserialize
data = auto_serialize(obj, "msgpack")
obj = auto_deserialize(data, "msgpack")
```

### 2. gRPC服务优化

**之前：**
```python
@grpc_service("user_service", address="localhost", port=9001)
class UserService:
    pass
```

**现在（推荐）：**
```python
from common.grpc import ServiceType, new_grpc_service, new_grpc_method

@new_grpc_service(ServiceType.LOGIC)
class UserService:
    @new_grpc_method()
    async def get_user(self, user_id: str):
        pass
```

**环境变量配置：**
```bash
export LOGIC_SERVICES="localhost:9001,localhost:9002"
export CHAT_SERVICES="localhost:9101,localhost:9102"
```

### 3. Repository访问控制

**之前（不推荐）：**
```python
# 直接访问Repository
from common.database.repositories import PlayerRepository
repo = PlayerRepository(redis, mongo)
player = await repo.get("player123")
```

**现在（推荐）：**
```python
# 通过Service层访问
from services.logic.services import PlayerService
service = PlayerService()
player = await service.get_player_info("player123")
```

### 4. 错误处理

**之前：**
```python
try:
    result = some_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    # 手动处理错误
```

**现在：**
```python
from common.utils import handle_errors, ErrorHandler

@handle_errors(reraise=True)
async def some_operation():
    # 自动错误处理和日志记录
    pass
```

### 5. 数据验证

**之前：**
```python
if not player_id or len(player_id) < 10:
    raise ValueError("Invalid player ID")
```

**现在：**
```python
from common.utils import validate_data, Validator

validate_data({"player_id": player_id}, {
    "player_id": [Validator.required, Validator.player_id_format]
})
```

## 迁移步骤

### 阶段1：渐进式迁移（推荐）

1. **新代码使用新接口**
   - 新的服务类使用 `new_grpc_service` 装饰器
   - 新的业务逻辑使用统一工具模块
   - 新的数据访问通过Service层

2. **现有代码保持兼容**
   - 原有的API继续工作
   - 逐步替换高频使用的模块

### 阶段2：全面迁移

1. **更新gRPC服务**
   ```python
   # 替换装饰器
   # @grpc_service("service_name", "localhost", 9001)
   @new_grpc_service(ServiceType.LOGIC)
   ```

2. **更新Repository访问**
   ```python
   # 删除直接Repository导入
   # from common.database.repositories import PlayerRepository
   
   # 使用Service层
   from services.logic.services import PlayerService
   ```

3. **更新错误处理**
   ```python
   # 添加装饰器
   from common.utils import handle_errors
   
   @handle_errors()
   async def your_function():
       pass
   ```

## 测试验证

运行以下测试确保迁移成功：

```bash
# 单元测试
poetry run python -m pytest test/unit/ -v

# 集成测试
poetry run python -m pytest test/integration/ -v

# 示例代码
python test/examples/excel_to_json_example.py
python test/examples/config_gen_example.py
```

## 常见问题

### Q: 原有代码是否需要立即修改？
A: 不需要。新系统保持向后兼容，原有代码继续工作。

### Q: 如何配置服务地址？
A: 通过环境变量或在ServiceRegistry中注册：
```python
registry = get_service_registry()
registry.register_service(ServiceType.LOGIC, "localhost", 9001)
```

### Q: Repository访问被阻止怎么办？
A: 这是预期行为。请通过Service层访问数据：
```python
# 错误的方式
repo = get_repository_manager().get_repository("player")  # PermissionError

# 正确的方式
service = PlayerService()  # 内部会正确访问Repository
```

### Q: 如何调试新的错误处理系统？
A: 错误处理器会自动记录详细日志：
```python
from common.utils import get_error_handler
handler = get_error_handler()
# 检查日志输出
```

## 性能影响

- **序列化**：零性能影响，仍使用原有实现
- **gRPC**：增加了服务发现，轻微开销但提高了可靠性
- **Repository**：增加了权限检查，开销极小
- **错误处理**：异步处理，对性能影响最小

## 技术支持

如有问题请查看：
- 单元测试：`test/unit/`
- 使用示例：`test/examples/` 
- 原始实现：各模块保持向后兼容

## 总结

本次重构在保持向后兼容的同时，大幅提升了代码的：
- **可维护性**：统一的工具和接口
- **安全性**：Repository访问控制
- **可靠性**：自动服务发现和错误处理
- **可扩展性**：模块化设计便于扩展