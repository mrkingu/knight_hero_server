# 游戏服务器框架编码规范

**版本**: 2.0  
**更新日期**: 2025-06-20  
**作者**: mrkingu

## 1. 命名规范

### 1.1 类名
使用 **PascalCase** (大驼峰) 命名：
```python
class PlayerService:        # ✓ 正确
class ItemRepository:       # ✓ 正确
class playerService:        # ✗ 错误
class Player_Service:       # ✗ 错误
```

### 1.2 函数和方法名
使用 **snake_case** (小写下划线) 命名：
```python
def get_player_info():      # ✓ 正确
def add_diamond():          # ✓ 正确
def getPlayerInfo():        # ✗ 错误
def AddDiamond():           # ✗ 错误
```

### 1.3 常量
使用 **UPPER_SNAKE_CASE** (大写下划线) 命名：
```python
MAX_LEVEL = 100             # ✓ 正确
DEFAULT_TIMEOUT = 30        # ✓ 正确
ERROR_CODES = {...}         # ✓ 正确
max_level = 100             # ✗ 错误
```

### 1.4 私有成员
使用 **前导下划线** 标识：
```python
class Service:
    def __init__(self):
        self._internal_cache = {}       # ✓ 私有属性
        
    def _internal_method(self):         # ✓ 私有方法
        pass
```

### 1.5 模块和包名
使用 **小写字母和下划线**：
```python
# 模块名
player_service.py           # ✓ 正确
item_repository.py          # ✓ 正确
PlayerService.py            # ✗ 错误

# 包名
common/database/            # ✓ 正确
common/utils/               # ✓ 正确
Common/Database/            # ✗ 错误
```

## 2. 文档规范

### 2.1 模块文档
每个模块文件开头必须包含文档字符串：
```python
"""
玩家服务模块
Player Service Module

作者: mrkingu
日期: 2025-06-20
描述: 处理玩家相关的业务逻辑，包括玩家信息管理、资源操作等
"""
```

### 2.2 类文档
使用Google风格的docstring：
```python
class PlayerService:
    """
    玩家服务类
    
    提供玩家相关的业务逻辑处理，包括：
    - 玩家信息查询和更新
    - 资源管理（钻石、经验等）
    - 登录状态维护
    
    Attributes:
        _cache: 玩家数据缓存
        _config: 服务配置
    """
```

### 2.3 方法文档
所有公开方法必须有docstring：
```python
async def get_player_info(self, player_id: str) -> Dict[str, Any]:
    """
    获取玩家信息
    
    Args:
        player_id: 玩家ID
        
    Returns:
        包含玩家信息的字典，格式：
        {
            "code": 0,
            "data": {
                "player_id": str,
                "nickname": str,
                "level": int,
                ...
            }
        }
        
    Raises:
        PlayerNotFoundError: 玩家不存在
        ValidationError: 参数验证失败
    """
```

## 3. 导入规范

### 3.1 导入顺序
严格按照以下顺序分组导入，组间空一行：
```python
# 1. 标准库导入
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

# 2. 第三方库导入
from fastapi import FastAPI
from pydantic import BaseModel
import redis

# 3. 本地模块导入
from common.ioc import service, autowired
from common.exceptions import GameException
from services.logic.services.base import BaseLogicService
```

### 3.2 导入规则
- 使用绝对导入，避免相对导入
- 每行只导入一个模块
- 按字母顺序排列同组内的导入

```python
# ✓ 正确
from common.ioc import service
from common.ioc import autowired
from common.database import BaseRepository

# ✗ 错误
from common.ioc import service, autowired
from .base import BaseService  # 相对导入
```

## 4. 异步编程规范

### 4.1 异步函数声明
所有IO操作必须声明为异步：
```python
# ✓ 正确 - 数据库操作
async def get_player_from_db(self, player_id: str) -> Optional[Dict]:
    return await self.repository.find_by_id(player_id)

# ✓ 正确 - 网络请求
async def call_external_api(self, url: str) -> Dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# ✗ 错误 - 阻塞操作
def get_player_from_db(self, player_id: str) -> Optional[Dict]:
    return self.repository.find_by_id(player_id)  # 同步调用
```

### 4.2 并发操作
合理使用 `asyncio.gather` 进行并发：
```python
# ✓ 正确 - 并发获取多个玩家信息
async def get_multiple_players(self, player_ids: List[str]) -> List[Dict]:
    tasks = [self.get_player_info(pid) for pid in player_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]

# ✗ 错误 - 串行执行
async def get_multiple_players(self, player_ids: List[str]) -> List[Dict]:
    results = []
    for pid in player_ids:
        result = await self.get_player_info(pid)  # 串行执行，性能差
        results.append(result)
    return results
```

### 4.3 异常处理
在异步函数中正确处理异常：
```python
async def safe_operation(self):
    try:
        result = await self.risky_operation()
        return result
    except SpecificException as e:
        self.logger.warning(f"Expected error: {e}")
        return None
    except Exception as e:
        self.logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
```

## 5. 错误处理规范

### 5.1 自定义异常
使用明确的自定义异常类：
```python
class GameException(Exception):
    """游戏异常基类"""
    
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

class PlayerNotFoundError(GameException):
    """玩家不存在异常"""
    
    def __init__(self, player_id: str):
        super().__init__(
            code=404,
            message=f"Player not found: {player_id}",
            data={"player_id": player_id}
        )
```

### 5.2 异常捕获层级
在适当的层级捕获和处理异常：
```python
# Service层 - 处理业务异常
class PlayerService:
    async def get_player_info(self, player_id: str) -> Dict:
        try:
            player_data = await self.repository.find_by_id(player_id)
            if not player_data:
                raise PlayerNotFoundError(player_id)
            return self.success_response(player_data)
        except PlayerNotFoundError:
            raise  # 重新抛出业务异常
        except Exception as e:
            self.logger.error(f"Database error: {e}")
            raise DatabaseError("Failed to get player info")

# Handler层 - 处理所有异常并转换为响应
class PlayerHandler:
    async def handle_get_player_info(self, request: dict) -> dict:
        try:
            result = await self.player_service.get_player_info(request["player_id"])
            return result
        except PlayerNotFoundError as e:
            return self.error_response(e.message, e.code)
        except Exception as e:
            self.logger.error(f"Handler error: {e}")
            return self.error_response("Internal server error", -999)
```

## 6. 类型注解规范

### 6.1 基本类型注解
所有函数参数和返回值必须添加类型注解：
```python
from typing import Dict, List, Optional, Any, Union

def process_data(data: Dict[str, Any], count: int = 10) -> List[str]:
    """处理数据并返回字符串列表"""
    pass

async def get_player_info(self, player_id: str) -> Optional[Dict[str, Any]]:
    """获取玩家信息，可能返回None"""
    pass
```

### 6.2 复杂类型注解
对于复杂的数据结构，使用 TypedDict 或 Pydantic 模型：
```python
from typing import TypedDict

class PlayerInfo(TypedDict):
    player_id: str
    nickname: str
    level: int
    diamond: int
    created_at: int

async def get_player_info(self, player_id: str) -> PlayerInfo:
    """返回标准的玩家信息格式"""
    pass
```

## 7. 代码组织规范

### 7.1 文件结构
```python
# 1. 模块文档字符串
"""模块说明"""

# 2. 导入部分（按规范分组）
import asyncio
from typing import Dict

from fastapi import FastAPI

from common.ioc import service

# 3. 常量定义
MAX_RETRY_COUNT = 3
DEFAULT_TIMEOUT = 30

# 4. 类型定义
class PlayerData(TypedDict):
    pass

# 5. 主要类定义
class PlayerService:
    pass

# 6. 辅助函数
def helper_function():
    pass
```

### 7.2 类内部组织
```python
class PlayerService:
    # 1. 类文档字符串
    """服务类说明"""
    
    # 2. 类变量
    SERVICE_NAME = "PlayerService"
    
    # 3. 初始化方法
    def __init__(self):
        pass
    
    # 4. IoC相关方法（装饰器声明的依赖）
    @autowired("PlayerRepository")
    def repository(self):
        pass
    
    # 5. 生命周期方法
    async def on_initialize(self):
        pass
    
    # 6. 公开业务方法（按字母顺序）
    async def add_diamond(self):
        pass
        
    async def get_player_info(self):
        pass
    
    # 7. 私有辅助方法
    def _validate_player_id(self):
        pass
```

## 8. 性能规范

### 8.1 缓存使用
合理使用缓存提升性能：
```python
from functools import lru_cache
from common.cache import async_cached

class PlayerService:
    @async_cached(ttl=300)  # 缓存5分钟
    async def get_player_info(self, player_id: str) -> Dict:
        """获取玩家信息，使用缓存"""
        return await self.repository.find_by_id(player_id)
    
    @lru_cache(maxsize=1000)
    def calculate_level_exp(self, level: int) -> int:
        """计算等级经验，使用内存缓存"""
        return level * 1000 + level ** 2
```

### 8.2 批量操作
优先使用批量操作而非循环：
```python
# ✓ 正确 - 批量操作
async def update_multiple_players(self, updates: List[Dict]) -> List[Dict]:
    return await self.repository.bulk_update(updates)

# ✗ 错误 - 循环操作
async def update_multiple_players(self, updates: List[Dict]) -> List[Dict]:
    results = []
    for update in updates:
        result = await self.repository.update(update)  # 多次数据库调用
        results.append(result)
    return results
```

## 9. 测试规范

### 9.1 测试文件命名
测试文件以 `test_` 开头：
```
test_player_service.py      # ✓ 正确
test_item_repository.py     # ✓ 正确
player_service_test.py      # ✗ 错误
```

### 9.2 测试方法命名
测试方法以 `test_` 开头，清晰描述测试内容：
```python
class TestPlayerService:
    async def test_get_player_info_success(self):
        """测试成功获取玩家信息"""
        pass
    
    async def test_get_player_info_not_found(self):
        """测试玩家不存在的情况"""
        pass
    
    async def test_add_diamond_invalid_amount(self):
        """测试添加钻石数量无效的情况"""
        pass
```

## 10. 安全规范

### 10.1 输入验证
所有外部输入必须进行验证：
```python
def validate_player_id(self, player_id: str) -> bool:
    """验证玩家ID格式"""
    if not player_id or len(player_id) < 6:
        return False
    if not player_id.isalnum():
        return False
    return True

async def handle_request(self, request: dict) -> dict:
    player_id = request.get("player_id", "")
    if not self.validate_player_id(player_id):
        return self.error_response("Invalid player_id")
```

### 10.2 敏感信息
避免在日志中记录敏感信息：
```python
# ✓ 正确
self.logger.info(f"Player login: {player_id}")

# ✗ 错误
self.logger.info(f"Player login: {player_id} password: {password}")
```

## 11. 工具配置

### 11.1 代码格式化
使用 Black 进行代码格式化：
```bash
black . --line-length 100
```

### 11.2 导入排序
使用 isort 进行导入排序：
```bash
isort . --profile black
```

### 11.3 代码检查
使用 pylint 进行代码检查：
```bash
pylint common/ services/ --max-line-length=100
```

## 12. 提交规范

### 12.1 提交信息格式
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

类型说明：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构代码
- `test`: 测试相关
- `chore`: 构建或辅助工具的变动

示例：
```
feat(player): add diamond management functionality

- Add add_diamond method to PlayerService
- Add consume_diamond method with validation
- Update player repository with diamond operations

Fixes #123
```

这个编码规范将确保代码的一致性、可读性和可维护性，为团队协作提供清晰的指导。