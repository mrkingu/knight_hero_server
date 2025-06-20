# Scripts Directory

## Repository Generation

### generate_repositories.py

自动扫描所有Model并生成对应的Repository类。

#### 使用方法

```bash
python scripts/generate_repositories.py
```

#### 功能

- 扫描 `common/database/models/` 目录下所有继承自 `BaseDocument` 的模型
- 为每个模型生成对应的Repository类
- 生成的Repository包含:
  - 基础CRUD操作 (get, create, update)
  - 自动生成的并发安全方法 (increment_*, decrement_*)
  - 根据Meta.concurrent_fields配置生成对应方法
- 输出到 `common/database/repositories/generated/` 目录
- 自动生成 `__init__.py` 文件

#### 示例输出

```
Scanning models...
Found 3 models

Generating repositories...
  Generating repository for PlayerModel
  Generating repository for GuildModel  
  Generating repository for ItemModel

Done! Generated repositories in: /path/to/repositories/generated
```

#### 注意事项

- 生成的文件会覆盖已存在的同名文件
- 请勿手动修改 `generated/` 目录下的文件
- 如需扩展功能，请在 `custom/` 目录下创建扩展文件
- 每次修改Model的Meta配置后，都应重新运行此脚本

#### 配置要求

Model必须包含正确的Meta类配置：

```python
class MyModel(BaseDocument):
    class Meta:
        concurrent_fields = {
            "field_name": {
                "type": "number",
                "operations": ["incr", "decr"],  # 支持的操作
                "min": 0,                        # 最小值(可选)
                "max": 999999                    # 最大值(可选)
            }
        }
```