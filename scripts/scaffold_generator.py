#!/usr/bin/env python3
"""
脚手架生成器
Scaffolding Generator

作者: mrkingu
日期: 2025-06-20
描述: 快速生成标准化的代码模板，支持Service、Handler、Model等组件
"""
import click
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def get_template_vars(name: str, module: str = "logic", description: str = "") -> Dict[str, Any]:
    """获取模板变量"""
    return {
        "name": name,
        "name_lower": name.lower(),
        "name_snake": "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_"),
        "module": module,
        "description": description or f"处理{name}相关业务逻辑",
        "author": "Developer",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "year": datetime.now().year
    }


def render_template(template: str, **kwargs) -> str:
    """渲染模板"""
    for key, value in kwargs.items():
        placeholder = "{{ " + key + " }}"
        template = template.replace(placeholder, str(value))
    return template


# 模板定义
TEMPLATES = {
    'service': '''"""
{{ name }}服务
{{ name }} Service

作者: {{ author }}
日期: {{ date }}
描述: {{ description }}
"""
from typing import Dict, Any, Optional, List
import logging

from common.ioc import service, autowired
from common.base import BaseGameService
from common.exceptions import (
    ValidationError, BusinessError, ResourceNotFoundError,
    {{ name }}NotFoundError, InsufficientResourceError
)
from common.performance import async_cached, monitor_performance


@service("{{ name }}Service")
class {{ name }}Service(BaseGameService):
    """{{ name }}服务实现"""
    
    @autowired("{{ name }}Repository")
    def repository(self):
        """{{ name_lower }}数据仓库"""
        pass
    
    async def on_initialize(self):
        """初始化服务"""
        await super().on_initialize()
        self.logger.info(f"{{ name }}Service initialized successfully")
        
    @monitor_performance("{{ name_snake }}_create")
    async def create_{{ name_snake }}(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建{{ name_lower }}
        
        Args:
            data: {{ name_lower }}数据
            
        Returns:
            创建结果
            
        Raises:
            ValidationError: 参数验证失败
            BusinessError: 业务逻辑错误
        """
        try:
            # 1. 参数验证
            self._validate_create_params(data)
            
            # 2. 业务逻辑验证
            await self._validate_create_business(data)
            
            # 3. 执行创建
            result = await self.repository.create(data)
            
            # 4. 记录业务日志
            await self.log_business_action(
                data.get("player_id", "system"),
                "create_{{ name_snake }}",
                data,
                result
            )
            
            return self.success_response(result, "{{ name }} created successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to create {{ name_lower }}: {e}")
            if isinstance(e, (ValidationError, BusinessError)):
                raise
            raise BusinessError(500, f"Failed to create {{ name_lower }}")
    
    @async_cached(ttl=300)
    @monitor_performance("{{ name_snake }}_get")
    async def get_{{ name_snake }}(self, {{ name_snake }}_id: str) -> Dict[str, Any]:
        """
        获取{{ name_lower }}信息
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            
        Returns:
            {{ name_lower }}信息
            
        Raises:
            {{ name }}NotFoundError: {{ name }}不存在
        """
        {{ name_snake }}_data = await self.repository.find_by_id({{ name_snake }}_id)
        
        if not {{ name_snake }}_data:
            raise {{ name }}NotFoundError({{ name_snake }}_id)
        
        return self.success_response({{ name_snake }}_data)
    
    @monitor_performance("{{ name_snake }}_update")
    async def update_{{ name_snake }}(
        self, 
        {{ name_snake }}_id: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        更新{{ name_lower }}
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            data: 更新数据
            
        Returns:
            更新结果
        """
        # 检查{{ name_lower }}是否存在
        existing = await self.repository.find_by_id({{ name_snake }}_id)
        if not existing:
            raise {{ name }}NotFoundError({{ name_snake }}_id)
        
        # 验证更新数据
        self._validate_update_params(data)
        
        # 执行更新
        result = await self.repository.update({{ name_snake }}_id, data)
        
        # 清除缓存
        await self.clear_cache(f"get_{{ name_snake }}:{{{ name_snake }}_id}")
        
        return self.success_response(result, "{{ name }} updated successfully")
    
    @monitor_performance("{{ name_snake }}_delete")
    async def delete_{{ name_snake }}(self, {{ name_snake }}_id: str) -> Dict[str, Any]:
        """
        删除{{ name_lower }}
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            
        Returns:
            删除结果
        """
        # 检查{{ name_lower }}是否存在
        existing = await self.repository.find_by_id({{ name_snake }}_id)
        if not existing:
            raise {{ name }}NotFoundError({{ name_snake }}_id)
        
        # 执行删除
        await self.repository.delete({{ name_snake }}_id)
        
        # 清除缓存
        await self.clear_cache(f"get_{{ name_snake }}:{{{ name_snake }}_id}")
        
        return self.success_response(None, "{{ name }} deleted successfully")
    
    def _validate_create_params(self, data: Dict[str, Any]) -> None:
        """验证创建参数"""
        required_fields = ["name"]  # 根据实际需求修改
        
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"Missing required field: {field}")
    
    def _validate_update_params(self, data: Dict[str, Any]) -> None:
        """验证更新参数"""
        if not data:
            raise ValidationError("Update data cannot be empty")
    
    async def _validate_create_business(self, data: Dict[str, Any]) -> None:
        """验证创建业务逻辑"""
        # 示例：检查名称是否重复
        name = data.get("name")
        if name:
            existing = await self.repository.find_by_name(name)
            if existing:
                raise BusinessError(409, f"{{ name }} with name '{name}' already exists")


class {{ name }}NotFoundError(ResourceNotFoundError):
    """{{ name }}不存在异常"""
    
    def __init__(self, {{ name_snake }}_id: str):
        super().__init__("{{ name }}", {{ name_snake }}_id)
''',

    'handler': '''"""
{{ name }}请求处理器
{{ name }} Request Handler

作者: {{ author }}
日期: {{ date }}
描述: {{ description }}
"""
from typing import Dict, Any
import logging

from common.ioc import service, autowired
from common.base import DictHandler
from common.exceptions import ValidationError
from common.performance import monitor_performance


@service("{{ name }}Handler")
class {{ name }}Handler(DictHandler):
    """{{ name }}请求处理器"""
    
    @autowired("{{ name }}Service")
    def service(self):
        """{{ name }}业务服务"""
        pass
        
    async def on_initialize(self) -> None:
        """初始化Handler"""
        await super().on_initialize()
        self.logger.info("{{ name }}Handler initialized")
    
    @monitor_performance("{{ name_snake }}_handler_validate")
    async def validate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """验证请求参数"""
        # 提取并验证基础参数
        action = request.get("action")
        if not action:
            raise ValidationError("Missing action parameter")
        
        # 根据action验证具体参数
        if action == "create":
            self._validate_create_request(request)
        elif action == "get":
            self._validate_get_request(request)
        elif action == "update":
            self._validate_update_request(request)
        elif action == "delete":
            self._validate_delete_request(request)
        else:
            raise ValidationError(f"Unknown action: {action}")
        
        return request
        
    @monitor_performance("{{ name_snake }}_handler_process")
    async def process(self, request: Dict[str, Any]) -> Any:
        """处理业务逻辑"""
        action = request["action"]
        
        if action == "create":
            return await self._handle_create(request)
        elif action == "get":
            return await self._handle_get(request)
        elif action == "update":
            return await self._handle_update(request)
        elif action == "delete":
            return await self._handle_delete(request)
        else:
            raise ValidationError(f"Unsupported action: {action}")
    
    async def _handle_create(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建请求"""
        create_data = {
            "name": request.get("name"),
            "description": request.get("description", ""),
            "player_id": self.extract_player_id(request)
        }
        
        return await self.service.create_{{ name_snake }}(create_data)
    
    async def _handle_get(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取请求"""
        {{ name_snake }}_id = request.get("{{ name_snake }}_id")
        return await self.service.get_{{ name_snake }}({{ name_snake }}_id)
    
    async def _handle_update(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理更新请求"""
        {{ name_snake }}_id = request.get("{{ name_snake }}_id")
        update_data = {
            key: value for key, value in request.items() 
            if key not in ["action", "{{ name_snake }}_id"]
        }
        
        return await self.service.update_{{ name_snake }}({{ name_snake }}_id, update_data)
    
    async def _handle_delete(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理删除请求"""
        {{ name_snake }}_id = request.get("{{ name_snake }}_id")
        return await self.service.delete_{{ name_snake }}({{ name_snake }}_id)
    
    def _validate_create_request(self, request: Dict[str, Any]) -> None:
        """验证创建请求"""
        self.validate_required_params(request, ["name"])
        
        name = request.get("name", "")
        if len(name) < 1 or len(name) > 100:
            raise ValidationError("Name must be 1-100 characters")
    
    def _validate_get_request(self, request: Dict[str, Any]) -> None:
        """验证获取请求"""
        self.validate_required_params(request, ["{{ name_snake }}_id"])
    
    def _validate_update_request(self, request: Dict[str, Any]) -> None:
        """验证更新请求"""
        self.validate_required_params(request, ["{{ name_snake }}_id"])
        
        # 至少要有一个更新字段
        update_fields = [key for key in request.keys() 
                        if key not in ["action", "{{ name_snake }}_id"]]
        if not update_fields:
            raise ValidationError("At least one field must be provided for update")
    
    def _validate_delete_request(self, request: Dict[str, Any]) -> None:
        """验证删除请求"""
        self.validate_required_params(request, ["{{ name_snake }}_id"])
''',

    'repository': '''"""
{{ name }}数据仓库
{{ name }} Repository

作者: {{ author }}
日期: {{ date }}
描述: {{ description }}
"""
from typing import Dict, Any, Optional, List
import logging

from common.ioc import repository
from common.database import BaseRepository
from common.performance import async_cached, monitor_performance


@repository("{{ name }}Repository")
class {{ name }}Repository(BaseRepository):
    """{{ name }}数据仓库"""
    
    def __init__(self):
        super().__init__()
        self.collection_name = "{{ name_snake }}s"
    
    @monitor_performance("{{ name_snake }}_repo_create")
    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建{{ name_lower }}
        
        Args:
            data: {{ name_lower }}数据
            
        Returns:
            创建的{{ name_lower }}
        """
        # 添加创建时间
        import time
        data["created_at"] = int(time.time())
        data["updated_at"] = data["created_at"]
        
        # 生成ID
        if "{{ name_snake }}_id" not in data:
            data["{{ name_snake }}_id"] = self.generate_id("{{ name_snake }}")
        
        # 插入数据库
        result = await self.insert_one(self.collection_name, data)
        
        return data
    
    @async_cached(ttl=300)
    @monitor_performance("{{ name_snake }}_repo_find_by_id")
    async def find_by_id(self, {{ name_snake }}_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID查找{{ name_lower }}
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            
        Returns:
            {{ name_lower }}数据或None
        """
        return await self.find_one(
            self.collection_name, 
            {"{{ name_snake }}_id": {{ name_snake }}_id}
        )
    
    @monitor_performance("{{ name_snake }}_repo_find_by_name")
    async def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        根据名称查找{{ name_lower }}
        
        Args:
            name: {{ name }}名称
            
        Returns:
            {{ name_lower }}数据或None
        """
        return await self.find_one(
            self.collection_name,
            {"name": name}
        )
    
    @monitor_performance("{{ name_snake }}_repo_update")
    async def update(self, {{ name_snake }}_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新{{ name_lower }}
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            data: 更新数据
            
        Returns:
            更新后的{{ name_lower }}
        """
        # 添加更新时间
        import time
        data["updated_at"] = int(time.time())
        
        # 更新数据库
        await self.update_one(
            self.collection_name,
            {"{{ name_snake }}_id": {{ name_snake }}_id},
            {"$set": data}
        )
        
        # 返回更新后的数据
        return await self.find_by_id({{ name_snake }}_id)
    
    @monitor_performance("{{ name_snake }}_repo_delete")
    async def delete(self, {{ name_snake }}_id: str) -> bool:
        """
        删除{{ name_lower }}
        
        Args:
            {{ name_snake }}_id: {{ name }}ID
            
        Returns:
            是否删除成功
        """
        result = await self.delete_one(
            self.collection_name,
            {"{{ name_snake }}_id": {{ name_snake }}_id}
        )
        
        return result.deleted_count > 0
    
    @monitor_performance("{{ name_snake }}_repo_list")
    async def list_{{ name_snake }}s(
        self, 
        page: int = 1, 
        page_size: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        获取{{ name_lower }}列表
        
        Args:
            page: 页码
            page_size: 每页大小
            filters: 过滤条件
            
        Returns:
            分页结果
        """
        query = filters or {}
        
        # 计算总数
        total = await self.count(self.collection_name, query)
        
        # 获取数据
        skip = (page - 1) * page_size
        items = await self.find_many(
            self.collection_name,
            query,
            skip=skip,
            limit=page_size,
            sort=[("created_at", -1)]
        )
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": skip + page_size < total
        }
''',

    'model': '''"""
{{ name }}数据模型
{{ name }} Data Model

作者: {{ author }}
日期: {{ date }}
描述: {{ description }}
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class {{ name }}Base(BaseModel):
    """{{ name }}基础模型"""
    
    name: str = Field(..., description="{{ name }}名称", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="{{ name }}描述", max_length=500)


class {{ name }}Create({{ name }}Base):
    """创建{{ name }}模型"""
    
    player_id: Optional[str] = Field(None, description="创建者ID")


class {{ name }}Update(BaseModel):
    """更新{{ name }}模型"""
    
    name: Optional[str] = Field(None, description="{{ name }}名称", min_length=1, max_length=100)
    description: Optional[str] = Field(None, description="{{ name }}描述", max_length=500)


class {{ name }}({{ name }}Base):
    """{{ name }}完整模型"""
    
    {{ name_snake }}_id: str = Field(..., description="{{ name }}ID")
    player_id: Optional[str] = Field(None, description="创建者ID")
    created_at: int = Field(..., description="创建时间戳")
    updated_at: int = Field(..., description="更新时间戳")
    
    class Config:
        # 示例配置
        schema_extra = {
            "example": {
                "{{ name_snake }}_id": "{{ name_snake }}_123456",
                "name": "示例{{ name }}",
                "description": "这是一个示例{{ name }}",
                "player_id": "player_123",
                "created_at": 1703980800,
                "updated_at": 1703980800
            }
        }


class {{ name }}List(BaseModel):
    """{{ name }}列表模型"""
    
    items: List[{{ name }}] = Field(..., description="{{ name }}列表")
    total: int = Field(..., description="总数量")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    has_next: bool = Field(..., description="是否有下一页")


class {{ name }}Response(BaseModel):
    """{{ name }}响应模型"""
    
    code: int = Field(0, description="响应码")
    message: str = Field("success", description="响应消息")
    data: Optional[{{ name }}] = Field(None, description="{{ name }}数据")
    timestamp: int = Field(..., description="响应时间戳")


class {{ name }}ListResponse(BaseModel):
    """{{ name }}列表响应模型"""
    
    code: int = Field(0, description="响应码")
    message: str = Field("success", description="响应消息")
    data: Optional[{{ name }}List] = Field(None, description="{{ name }}列表数据")
    timestamp: int = Field(..., description="响应时间戳")
'''
}


@click.group()
def cli():
    """游戏服务器框架脚手架生成器"""
    pass


@cli.command()
@click.option('--type', 'component_type', 
              type=click.Choice(['service', 'handler', 'repository', 'model']), 
              required=True, help='组件类型')
@click.option('--name', required=True, help='组件名称 (PascalCase)')
@click.option('--module', default='logic', help='模块名称 (logic/chat/fight)')
@click.option('--description', help='组件描述')
@click.option('--output-dir', help='输出目录 (可选)')
def generate(component_type: str, name: str, module: str, description: str, output_dir: str):
    """生成标准化代码模板"""
    
    # 验证名称格式
    if not name[0].isupper():
        click.echo("Error: Component name must be in PascalCase (e.g., PlayerService)")
        return
    
    # 获取模板变量
    template_vars = get_template_vars(name, module, description)
    
    # 获取模板
    if component_type not in TEMPLATES:
        click.echo(f"Error: Template not found for type: {component_type}")
        return
    
    template = TEMPLATES[component_type]
    
    # 渲染模板
    content = render_template(template, **template_vars)
    
    # 确定输出路径
    if output_dir:
        output_path = Path(output_dir)
    else:
        base_path = Path.cwd()
        
        if component_type == 'service':
            output_path = base_path / f"services/{module}/services"
        elif component_type == 'handler':
            output_path = base_path / f"services/{module}/handlers"
        elif component_type == 'repository':
            output_path = base_path / f"services/{module}/repositories"
        else:  # model
            output_path = base_path / f"common/models"
    
    # 创建文件名
    if component_type == 'model':
        filename = f"{template_vars['name_snake']}_model.py"
    else:
        filename = f"{template_vars['name_snake']}_{component_type}.py"
    
    # 完整路径
    full_path = output_path / filename
    
    # 创建目录
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 检查文件是否已存在
    if full_path.exists():
        if not click.confirm(f"File {full_path} already exists. Overwrite?"):
            return
    
    # 写入文件
    try:
        full_path.write_text(content, encoding='utf-8')
        click.echo(f"Generated {component_type}: {full_path}")
        
        # 输出使用提示
        click.echo(f"\nNext steps:")
        if component_type == 'service':
            click.echo(f"1. 实现具体的业务逻辑方法")
            click.echo(f"2. 配置依赖注入的Repository")
            click.echo(f"3. 添加单元测试")
        elif component_type == 'handler':
            click.echo(f"1. 完善参数验证逻辑")
            click.echo(f"2. 配置路由映射")
            click.echo(f"3. 添加集成测试")
        elif component_type == 'repository':
            click.echo(f"1. 实现具体的数据访问方法")
            click.echo(f"2. 配置数据库连接")
            click.echo(f"3. 添加数据层测试")
        else:  # model
            click.echo(f"1. 根据实际需求调整字段定义")
            click.echo(f"2. 添加数据验证规则")
            click.echo(f"3. 配置序列化选项")
            
    except Exception as e:
        click.echo(f"Error writing file: {e}")


@cli.command()
@click.option('--name', required=True, help='完整模块名称')
@click.option('--module', default='logic', help='服务模块 (logic/chat/fight)')
def generate_module(name: str, module: str):
    """生成完整的模块 (Service + Handler + Repository + Model)"""
    
    click.echo(f"Generating complete module: {name}")
    
    components = ['model', 'repository', 'service', 'handler']
    
    for component_type in components:
        click.echo(f"\nGenerating {component_type}...")
        
        try:
            # 调用generate命令
            from click.testing import CliRunner
            runner = CliRunner()
            
            result = runner.invoke(generate, [
                '--type', component_type,
                '--name', name,
                '--module', module,
                '--description', f'{name} {component_type} for {module} module'
            ])
            
            if result.exit_code == 0:
                click.echo(f"✓ {component_type} generated successfully")
            else:
                click.echo(f"✗ Failed to generate {component_type}: {result.output}")
                
        except Exception as e:
            click.echo(f"✗ Error generating {component_type}: {e}")
    
    click.echo(f"\n🎉 Module {name} generated successfully!")
    click.echo(f"Location: services/{module}/")


@cli.command()
def list_templates():
    """列出所有可用的模板"""
    click.echo("Available templates:")
    for template_name in TEMPLATES.keys():
        click.echo(f"  - {template_name}")


if __name__ == '__main__':
    cli()