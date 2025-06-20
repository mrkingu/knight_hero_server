"""
Repository自动生成器
扫描Model并生成对应的Repository
作者: mrkingu
日期: 2025-06-20
"""
import inspect
import importlib
from pathlib import Path
from typing import Dict, Type, List
from jinja2 import Template
from ..models.base_document import BaseDocument

class RepositoryGenerator:
    """Repository生成器"""
    
    def __init__(self, model_path: str, output_path: str):
        """
        初始化生成器
        
        Args:
            model_path: Model所在路径
            output_path: Repository输出路径
        """
        self.model_path = Path(model_path)
        self.output_path = Path(output_path)
        self.models: Dict[str, Type] = {}
        
    def scan_models(self) -> Dict[str, Type]:
        """扫描所有Model"""
        for py_file in self.model_path.glob("*_model.py"):
            if py_file.name == "base_document.py":
                continue
                
            module_name = py_file.stem
            try:
                module = importlib.import_module(f"common.database.models.{module_name}")
                
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseDocument) and 
                        obj != BaseDocument):
                        self.models[name] = obj
            except ImportError as e:
                print(f"Warning: Could not import {module_name}: {e}")
                    
        return self.models
        
    def generate_repository(self, model_name: str, model_class: Type):
        """为单个Model生成Repository"""
        # 获取模型元数据
        meta = getattr(model_class, 'Meta', None)
        settings = getattr(model_class, 'Settings', None)
        
        # 准备模板数据
        template_data = {
            "model_name": model_name,
            "model_class": model_class.__name__,
            "collection_name": getattr(settings, 'name', model_name.lower()) if settings else model_name.lower(),
            "concurrent_fields": getattr(meta, 'concurrent_fields', {}) if meta else {},
            "cache_ttl": getattr(meta, 'cache_ttl', 300) if meta else 300,
            "indexes": getattr(meta, 'indexes', []) if meta else []
        }
        
        # 生成Repository代码
        repository_code = self._render_template(template_data)
        
        # 写入文件
        repo_name = model_name.replace("Model", "").lower()
        output_file = self.output_path / f"{repo_name}_repository.py"
        output_file.write_text(repository_code, encoding='utf-8')
        
    def _render_template(self, data: dict) -> str:
        """渲染Repository模板"""
        template = Template('''"""
{{ model_name.replace("Model", "") }}数据仓库
自动生成，请勿手动修改
生成时间: {{ now }}
"""
from typing import Dict, Any, Optional, List
from ...repository.base_repository import BaseRepository
from ...models.{{ model_name.lower().replace("model", "_model") }} import {{ model_class }}
from ...concurrent.operation_type import OperationType

class {{ model_name.replace("Model", "") }}Repository(BaseRepository[{{ model_class }}]):
    """{{ model_name.replace("Model", "") }}数据仓库"""
    
    def __init__(self, redis_client, mongo_client):
        super().__init__(
            redis_client=redis_client,
            mongo_client=mongo_client,
            collection_name="{{ collection_name }}"
        )
        
    def get_concurrent_fields(self) -> Dict[str, Dict[str, Any]]:
        """获取支持并发操作的字段"""
        return {{ concurrent_fields }}
        
    async def get_by_id(self, entity_id: str) -> Optional[{{ model_class }}]:
        """根据ID获取实体"""
        return await self.get(entity_id)
        
    async def create(self, data: Dict[str, Any]) -> {{ model_class }}:
        """创建新实体"""
        entity = {{ model_class }}(**data)
        await self.save(str(entity.id), entity)
        return entity
        
    async def update(self, entity_id: str, data: Dict[str, Any]) -> bool:
        """更新实体"""
        entity = await self.get(entity_id)
        if not entity:
            return False
            
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
                
        return await self.save(entity_id, entity)
        
    # 自动生成的并发安全方法
    {% for field, config in concurrent_fields.items() %}
    {% if "incr" in config.operations %}
    async def increment_{{ field }}(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """增加{{ field }}（并发安全）"""
        return await self.modify_field(
            entity_id=entity_id,
            field="{{ field }}",
            operation=OperationType.INCREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    {% endif %}
    
    {% if "decr" in config.operations %}
    async def decrement_{{ field }}(
        self,
        entity_id: str,
        amount: int,
        source: str = "unknown",
        reason: str = ""
    ) -> Dict[str, Any]:
        """减少{{ field }}（并发安全）"""
        # 先检查余额
        entity = await self.get(entity_id)
        if not entity or getattr(entity, "{{ field }}", 0) < amount:
            return {"success": False, "reason": "insufficient_balance"}
            
        return await self.modify_field(
            entity_id=entity_id,
            field="{{ field }}",
            operation=OperationType.DECREMENT.value,
            value=amount,
            source=source,
            metadata={"reason": reason}
        )
    {% endif %}
    {% endfor %}
''')
        
        from datetime import datetime
        data['now'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return template.render(data)