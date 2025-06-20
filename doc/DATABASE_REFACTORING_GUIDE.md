# Database Layer Refactoring - Usage Guide

## 概述

本文档展示Database层重构前后的对比，以及新的Repository自动生成系统的使用方法。

## 重构前后对比

### 重构前的问题

```python
# 老版本 - Model包含业务逻辑
class Player(BaseModel):
    player_id: str
    diamond: int = 0
    
# 业务逻辑混在模型中
def get_concurrent_fields(model_class):
    if model_class == Player:
        return {"diamond": {"operations": ["incr", "decr"]}}

# Repository需要手动实现每个方法
class PlayerRepository(BaseRepository):
    def get_concurrent_fields(self):
        return get_concurrent_fields(Player)  # 耦合
    
    async def add_diamond(self, player_id, amount, source):
        # 手动实现的方法
        return await self.modify_field(...)
```

### 重构后的优势

```python
# 新版本 - 纯数据模型
class PlayerModel(BaseDocument):
    """纯数据定义，不包含任何业务逻辑"""
    player_id: str = Field(..., description="玩家ID", index=True)
    diamond: int = Field(default=0, ge=0, description="钻石")
    
    class Meta:
        """元数据配置供Repository生成器使用"""
        concurrent_fields = {
            "diamond": {
                "type": "number", 
                "operations": ["incr", "decr"],
                "min": 0, "max": 999999999
            }
        }
        indexes = ["player_id"]
        cache_ttl = 300

# 自动生成的Repository - 无需手写
class PlayerRepository(BaseRepository[PlayerModel]):
    """自动生成，请勿手动修改"""
    
    async def increment_diamond(self, entity_id, amount, source, reason=""):
        """增加钻石（并发安全）- 自动生成"""
        return await self.modify_field(...)
    
    async def decrement_diamond(self, entity_id, amount, source, reason=""):
        """减少钻石（并发安全）- 自动生成"""
        # 自动包含余额检查
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "diamond", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
        return await self.modify_field(...)

# 业务逻辑在Service层
class PlayerService:
    def __init__(self, player_repository: PlayerRepository):
        self.player_repository = player_repository
    
    async def recharge_diamond(self, player_id, amount, order_id):
        """充值业务逻辑"""
        # 1. 业务验证
        if await self._check_order_processed(order_id):
            return {"success": False, "reason": "duplicate_order"}
        
        # 2. 调用Repository
        result = await self.player_repository.increment_diamond(
            entity_id=player_id, amount=amount, source="recharge"
        )
        
        # 3. 业务后处理
        if result["success"]:
            await self._mark_order_processed(order_id)
            await self._send_notification(player_id, amount)
        
        return result
```

## 自动生成系统使用

### 1. 定义Model

```python
# common/database/models/my_model.py
class MyModel(BaseDocument):
    """我的数据模型"""
    
    entity_id: str = Field(..., description="实体ID", index=True)
    currency: int = Field(default=0, description="货币")
    score: int = Field(default=0, description="积分")
    
    class Settings:
        name = "my_collection"  # MongoDB集合名
    
    class Meta:
        # 支持并发操作的字段
        concurrent_fields = {
            "currency": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999
            },
            "score": {
                "type": "number", 
                "operations": ["incr"],
                "min": 0
            }
        }
        # 索引定义
        indexes = ["entity_id", [("score", -1)]]
        # 缓存TTL
        cache_ttl = 600
```

### 2. 运行生成脚本

```bash
python scripts/generate_repositories.py
```

### 3. 自动生成的Repository

```python
# common/database/repositories/generated/my_repository.py (自动生成)
class MyRepository(BaseRepository[MyModel]):
    """My数据仓库 - 自动生成，请勿手动修改"""
    
    def get_concurrent_fields(self):
        return {
            "currency": {"type": "number", "operations": ["incr", "decr"], "min": 0, "max": 999999999},
            "score": {"type": "number", "operations": ["incr"], "min": 0}
        }
    
    async def increment_currency(self, entity_id, amount, source="unknown", reason=""):
        """增加currency（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id, field="currency", 
            operation=OperationType.INCREMENT.value,
            value=amount, source=source, metadata={"reason": reason}
        )
    
    async def decrement_currency(self, entity_id, amount, source="unknown", reason=""):
        """减少currency（并发安全）"""
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "currency", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
        return await self.modify_field(...)
    
    async def increment_score(self, entity_id, amount, source="unknown", reason=""):
        """增加score（并发安全）"""
        return await self.modify_field(...)
```

### 4. 在Service中使用

```python
# services/my_service.py
class MyService:
    def __init__(self, my_repository: MyRepository):
        self.my_repository = my_repository
    
    async def reward_player(self, player_id: str, currency: int, score: int):
        """奖励玩家 - 业务逻辑"""
        # 同时增加货币和积分
        currency_result = await self.my_repository.increment_currency(
            entity_id=player_id, amount=currency, source="reward"
        )
        
        if currency_result["success"]:
            score_result = await self.my_repository.increment_score(
                entity_id=player_id, amount=score, source="reward"
            )
            return {"currency": currency_result, "score": score_result}
        
        return {"success": False, "reason": "currency_update_failed"}
```

## 目录结构

```
common/database/
├── models/                     # 纯数据模型
│   ├── base_document.py       # 基础文档类
│   ├── player_model.py        # 玩家模型
│   └── my_model.py           # 自定义模型
├── repositories/
│   ├── generated/             # 自动生成的Repository
│   │   ├── player_repository.py
│   │   └── my_repository.py
│   ├── custom/               # 手动扩展Repository
│   │   └── player_repository_ext.py
│   └── [原有文件]            # 向后兼容
├── generator/                # 生成器系统
│   ├── repository_generator.py
│   └── repository_registry.py
└── [其他目录]
```

## 最佳实践

### 1. Model设计原则

- ✅ **只包含数据字段定义**
- ✅ **使用Meta类配置元数据**
- ✅ **添加适当的Field描述和验证**
- ❌ **不要在Model中写业务方法**
- ❌ **不要在Model中处理业务逻辑**

### 2. Repository使用原则

- ✅ **使用自动生成的Repository作为基础**
- ✅ **复杂查询在custom目录扩展**
- ✅ **利用并发安全的increment/decrement方法**
- ❌ **不要修改generated目录的文件**

### 3. Service设计原则

- ✅ **所有业务逻辑都在Service层**
- ✅ **通过Repository进行数据操作**
- ✅ **处理业务验证和后续流程**
- ✅ **记录业务日志和发送通知**

## 并发安全示例

```python
# 传统方式 - 可能有并发问题
player = await repo.get(player_id)
player.diamond += amount
await repo.save(player)

# 新方式 - 并发安全
result = await repo.increment_diamond(
    entity_id=player_id, 
    amount=amount, 
    source="reward"
)
```

## 扩展Repository

```python
# common/database/repositories/custom/player_repository_ext.py
class PlayerRepositoryExt:
    """玩家Repository扩展"""
    
    def __init__(self, base_repository: PlayerRepository):
        self.base = base_repository
    
    async def get_top_players_by_level(self, limit: int = 10):
        """获取等级排行榜 - 复杂查询"""
        # 实现复杂查询逻辑
        pass
    
    async def batch_reward_players(self, rewards: List[Dict]):
        """批量奖励玩家"""
        results = []
        for reward in rewards:
            result = await self.base.increment_diamond(
                entity_id=reward["player_id"],
                amount=reward["amount"],
                source="batch_reward"
            )
            results.append(result)
        return results
```

## 总结

重构后的Database层具有以下优势：

1. **职责分离明确**: Model(数据) → Repository(存取) → Service(业务)
2. **自动化程度高**: 新Model自动生成Repository，减少重复代码
3. **并发安全**: 自动生成的方法都经过并发安全处理
4. **易于维护**: 纯数据模型易于理解和修改
5. **可扩展性强**: 支持custom扩展和业务特定需求
6. **向后兼容**: 不影响现有代码正常运行