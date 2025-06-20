# 配置管理系统文档
Configuration Management System Documentation

## 概述 Overview

配置管理系统为骑士英雄游戏服务器提供了完整的配置文件管理解决方案，支持Excel转JSON、自动生成配置类、类型安全访问和热更新功能。

The configuration management system provides a complete configuration file management solution for the Knight Hero game server, supporting Excel to JSON conversion, automatic configuration class generation, type-safe access, and hot reloading.

## 核心特性 Core Features

### 1. Excel到JSON转换 Excel to JSON Conversion
- 支持`.xlsx`和`.xls`格式的Excel文件
- 自动类型推断和转换
- 批量转换功能
- 数据验证和错误报告

### 2. 自动配置类生成 Auto Configuration Class Generation
- 扫描JSON配置文件
- 自动生成Pydantic配置类
- 类型注解和字段验证
- 生成配置管理器

### 3. 配置加载器 Configuration Loader
- 启动时加载所有配置
- 内存缓存提高性能
- 支持热更新监控
- 配置版本管理

### 4. 类型安全访问 Type-safe Access
- 基于Pydantic的类型验证
- 自动类型转换
- 字段约束检查
- 完整的IDE支持

## 目录结构 Directory Structure

```
common/config/
├── __init__.py                 # 模块导出
├── base_config.py             # 基础配置类
├── excel_to_json.py           # Excel转JSON工具
├── config_gen.py              # 配置类生成器
├── config_loader.py           # 配置加载器
└── generated/                 # 自动生成的配置类
    ├── __init__.py
    └── auto_generated_configs.py

excel/                         # Excel配置文件目录
├── item.xlsx                  # 道具配置
├── skill.xlsx                 # 技能配置
└── npc.xlsx                   # NPC配置

json/                          # JSON配置文件目录
├── item.json                  # 道具配置JSON
├── skill.json                 # 技能配置JSON
└── npc.json                   # NPC配置JSON
```

## 使用指南 Usage Guide

### 基础使用 Basic Usage

```python
import asyncio
from common.config import initialize_configs, get_config_manager

async def main():
    # 初始化配置系统
    success = await initialize_configs()
    
    if success:
        # 获取配置管理器
        manager = get_config_manager()
        
        # 访问配置
        item = manager.get_item(1001)
        skill = manager.get_skill(2001)
        npc = manager.get_npc(3001)
        
        # 按类型获取配置
        type1_items = manager.get_items_by_type(1)
        
        print(f"道具: {item.name if item else 'Not found'}")

asyncio.run(main())
```

### Excel配置文件格式 Excel Configuration Format

Excel文件应包含以下结构：
- 第一行：数据类型定义 (int, str, float, bool, list)
- 从第二行开始：实际配置数据
- 第一列作为主键

示例Excel格式：

| item_id | name   | type | quality | price | description  |
|---------|--------|------|---------|-------|-------------|
| int     | str    | int  | int     | int   | str         |
| 1001    | 小血瓶  | 1    | 1       | 100   | 恢复100点生命值 |
| 1002    | 大血瓶  | 1    | 2       | 200   | 恢复300点生命值 |

### 配置转换工作流 Configuration Conversion Workflow

```python
from common.config import ExcelToJsonConverter, ConfigClassGenerator

# 1. Excel转JSON
converter = ExcelToJsonConverter()
results = converter.batch_convert()

# 2. 生成配置类
generator = ConfigClassGenerator()
gen_results = generator.generate_all_configs()

# 3. 加载配置
await initialize_configs()
```

### 热更新 Hot Reloading

```python
from common.config import ConfigLoader

# 启用热更新
loader = ConfigLoader(auto_reload=True)
await loader.load_all_configs()

# 添加重载回调
def on_config_reload(file_path):
    print(f"配置文件已重载: {file_path}")

loader.add_reload_callback(on_config_reload)
```

## 配置类型 Configuration Types

### 道具配置 Item Configuration

```python
class ItemConfig(BaseConfig):
    item_id: int = Field(description="道具ID")
    name: str = Field(description="道具名称")
    type: int = Field(description="道具类型")
    quality: int = Field(description="道具品质", ge=1, le=5)
    price: int = Field(description="道具价格", ge=0)
    description: str = Field(description="道具描述")
    max_stack: int = Field(default=1, description="最大堆叠数量", ge=1)
    level_requirement: int = Field(default=1, description="等级需求", ge=1)
```

### 技能配置 Skill Configuration

```python
class SkillConfig(BaseConfig):
    skill_id: int = Field(description="技能ID")
    name: str = Field(description="技能名称")
    type: int = Field(description="技能类型")
    level: int = Field(description="技能等级", ge=1)
    damage: int = Field(description="伤害值", ge=0)
    mana_cost: int = Field(description="魔法消耗", ge=0)
    cooldown: float = Field(description="冷却时间(秒)", ge=0)
    description: str = Field(description="技能描述")
```

### NPC配置 NPC Configuration

```python
class NpcConfig(BaseConfig):
    npc_id: int = Field(description="NPC ID")
    name: str = Field(description="NPC名称")
    level: int = Field(description="NPC等级", ge=1)
    hp: int = Field(description="生命值", ge=1)
    attack: int = Field(description="攻击力", ge=0)
    defense: int = Field(description="防御力", ge=0)
    drop_items: List[int] = Field(default_factory=list, description="掉落道具列表")
    ai_type: str = Field(description="AI类型")
```

## API参考 API Reference

### ConfigManager

```python
class ConfigManager:
    def get_item(self, item_id: int) -> Optional[ItemConfig]
    def get_skill(self, skill_id: int) -> Optional[SkillConfig]
    def get_npc(self, npc_id: int) -> Optional[NpcConfig]
    def get_items_by_type(self, item_type: int) -> List[ItemConfig]
    def get_skills_by_type(self, skill_type: int) -> List[SkillConfig]
    def get_config_count(self) -> Dict[str, int]
    def validate_all_configs(self) -> Dict[str, List[str]]
    def clear_all(self) -> None
```

### ExcelToJsonConverter

```python
class ExcelToJsonConverter:
    def __init__(self, excel_dir: str = "excel", json_dir: str = "json")
    def scan_excel_files(self) -> List[Path]
    def convert_file(self, excel_file: Path, output_file: Optional[Path] = None) -> bool
    def batch_convert(self) -> Dict[str, bool]
    def get_conversion_info(self) -> Dict[str, Any]
```

### ConfigLoader

```python
class ConfigLoader:
    def __init__(self, config_dir: str = "json", auto_reload: bool = False)
    async def load_all_configs(self) -> bool
    async def reload_all_configs(self) -> bool
    def add_reload_callback(self, callback: Callable[[str], None])
    def is_loaded(self) -> bool
    def get_config_versions(self) -> Dict[str, ConfigVersion]
```

## 测试 Testing

配置系统包含完整的测试套件，覆盖所有主要功能：

```bash
# 运行配置系统测试
python -m pytest test/test_config.py -v

# 运行特定测试类
python -m pytest test/test_config.py::TestConfigManager -v
```

测试涵盖：
- 基础配置类验证
- 配置管理器功能
- Excel转JSON转换
- 配置类自动生成
- 配置加载和热更新
- 完整工作流程集成测试

## 性能特性 Performance Features

### 内存缓存
- 所有配置在启动时加载到内存
- 避免重复的文件I/O操作
- 快速的配置访问性能

### 惰性加载
- 只在需要时解析配置文件
- 支持按需加载特定配置类型

### 批量操作
- 支持批量转换Excel文件
- 批量生成配置类
- 批量验证配置完整性

## 错误处理 Error Handling

### 数据验证错误
```python
try:
    item = ItemConfig(**invalid_data)
except ValidationError as e:
    print(f"配置验证失败: {e}")
```

### 文件处理错误
```python
converter = ExcelToJsonConverter()
results = converter.batch_convert()

for filename, success in results.items():
    if not success:
        print(f"转换失败: {filename}")
```

### 配置加载错误
```python
loader = ConfigLoader()
success = await loader.load_all_configs()

if not success:
    print("配置加载失败")
    # 检查具体错误
    errors = loader.config_manager.validate_all_configs()
    print(f"验证错误: {errors}")
```

## 扩展开发 Extension Development

### 添加新配置类型

1. 在Excel文件中定义新配置格式
2. 转换为JSON格式
3. 生成配置类或手动定义
4. 在ConfigManager中添加对应方法

```python
class NewConfig(BaseConfig):
    config_id: int = Field(description="配置ID")
    # 添加其他字段...

# 在ConfigManager中添加
def get_new_config(self, config_id: int) -> Optional[NewConfig]:
    return self.new_config.get(config_id)
```

### 自定义类型转换

```python
class CustomExcelToJsonConverter(ExcelToJsonConverter):
    def _convert_value(self, value: Any, target_type: str) -> Any:
        if target_type == 'custom_type':
            # 自定义转换逻辑
            return custom_conversion(value)
        return super()._convert_value(value, target_type)
```

## 最佳实践 Best Practices

### 配置文件组织
- 按功能模块分离配置文件
- 使用清晰的命名约定
- 保持配置文件结构一致

### 数据类型设计
- 为字段添加合适的验证约束
- 使用描述性的字段名称
- 提供默认值以保证向后兼容

### 版本管理
- 记录配置文件变更历史
- 使用版本号跟踪配置更新
- 实施配置迁移策略

### 性能优化
- 启用配置缓存
- 使用类型过滤减少查询
- 定期清理无用配置

## 故障排除 Troubleshooting

### 常见问题

**Q: Excel转换失败**
A: 检查Excel文件格式，确保第一行是类型定义，数据类型正确

**Q: 配置验证失败**
A: 检查字段类型和约束，确保数据符合Pydantic模型定义

**Q: 热更新不工作**
A: 确认auto_reload=True，检查文件权限和路径

**Q: 内存使用过高**
A: 考虑配置文件大小，使用配置分片或惰性加载

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查配置统计
manager = get_config_manager()
stats = manager.get_config_count()
print(f"配置统计: {stats}")

# 验证配置完整性
errors = manager.validate_all_configs()
if any(errors.values()):
    print(f"配置错误: {errors}")
```

---

## 作者 Author
lx - 2025-06-18

## 许可证 License
MIT License