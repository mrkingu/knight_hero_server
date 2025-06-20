"""
Repository生成器
自动扫描Document定义并生成对应的Repository类
作者: lx
日期: 2025-06-18
"""
import inspect
import logging
from typing import Type, Dict, Any, List, Optional, Union
from pathlib import Path

from beanie import Document

from .base_repository import BaseRepository
from .models import get_concurrent_fields, get_collection_name, ALL_DOCUMENT_MODELS
from .redis_cache import RedisCache
from .mongo_client import MongoClient

logger = logging.getLogger(__name__)


class RepositoryGenerator:
    """Repository自动生成器"""
    
    def __init__(self, redis_client: RedisCache, mongo_client: MongoClient):
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.generated_repositories: Dict[str, BaseRepository] = {}
    
    def generate_repository_class(self, document_class: Type[Document]) -> Type[BaseRepository]:
        """
        为指定Document类生成Repository类
        
        Args:
            document_class: Document类
            
        Returns:
            生成的Repository类
        """
        collection_name = get_collection_name(document_class)
        concurrent_fields = get_concurrent_fields(document_class)
        
        # 动态创建Repository类
        class_name = f"{document_class.__name__}Repository"
        
        class GeneratedRepository(BaseRepository):
            """动态生成的Repository类"""
            
            def __init__(self, redis_client: RedisCache, mongo_client: MongoClient):
                super().__init__(
                    redis_client=redis_client,
                    mongo_client=mongo_client,
                    collection_name=collection_name,
                    document_class=document_class
                )
            
            async def create_entity(self, **kwargs) -> Optional[Any]:
                """创建新实体"""
                try:
                    # 使用Document类的默认值
                    entity_data = {}
                    
                    # 获取Document类的字段定义
                    for field_name, field_info in document_class.model_fields.items():
                        if field_name in kwargs:
                            entity_data[field_name] = kwargs[field_name]
                        elif hasattr(field_info, 'default') and field_info.default is not None:
                            if callable(field_info.default):
                                entity_data[field_name] = field_info.default()
                            else:
                                entity_data[field_name] = field_info.default
                    
                    return await self.create(entity_data)
                    
                except Exception as e:
                    logger.error(f"创建 {document_class.__name__} 实体失败: {e}")
                    return None
        
        # 为每个并发字段生成专用方法
        for field_name, field_config in concurrent_fields.items():
            operations = field_config.get("operations", [])
            field_type = field_config.get("type", "any")
            
            # 生成增量方法
            if "incr" in operations:
                def make_increment_method(field):
                    async def increment_field(self, entity_id: str, amount, source: str = "", reason: str = "", **kwargs):
                        return await self.increment(entity_id, field, amount, source, reason, kwargs)
                    return increment_field
                
                method_name = f"add_{field_name}"
                setattr(GeneratedRepository, method_name, make_increment_method(field_name))
            
            # 生成减量方法
            if "decr" in operations:
                def make_decrement_method(field):
                    async def decrement_field(self, entity_id: str, amount, source: str = "", reason: str = "", **kwargs):
                        return await self.decrement_with_check(entity_id, field, amount, source, reason, kwargs)
                    return decrement_field
                
                method_name = f"consume_{field_name}"
                setattr(GeneratedRepository, method_name, make_decrement_method(field_name))
            
            # 生成设置方法
            if "set" in operations:
                def make_set_method(field):
                    async def set_field(self, entity_id: str, value, source: str = "", reason: str = "", **kwargs):
                        return await self.set_field(entity_id, field, value, source, reason, kwargs)
                    return set_field
                
                method_name = f"set_{field_name}"
                setattr(GeneratedRepository, method_name, make_set_method(field_name))
        
        # 设置类名
        GeneratedRepository.__name__ = class_name
        GeneratedRepository.__qualname__ = class_name
        
        return GeneratedRepository
    
    def generate_all_repositories(self) -> Dict[str, BaseRepository]:
        """生成所有Document的Repository"""
        repositories = {}
        
        for document_class in ALL_DOCUMENT_MODELS:
            try:
                repo_class = self.generate_repository_class(document_class)
                repo_instance = repo_class(self.redis_client, self.mongo_client)
                
                collection_name = get_collection_name(document_class)
                repositories[collection_name] = repo_instance
                
                logger.info(f"生成Repository: {repo_class.__name__} for {collection_name}")
                
            except Exception as e:
                logger.error(f"生成Repository失败: {document_class.__name__}, {e}")
        
        self.generated_repositories = repositories
        return repositories
    
    def get_repository(self, collection_name: str) -> Optional[BaseRepository]:
        """获取指定集合的Repository"""
        return self.generated_repositories.get(collection_name)
    
    def list_repositories(self) -> List[str]:
        """列出所有已生成的Repository"""
        return list(self.generated_repositories.keys())
    
    async def start_all_repositories(self, operation_logger) -> None:
        """启动所有Repository"""
        for repo in self.generated_repositories.values():
            await repo.start(operation_logger)
        
        logger.info(f"启动了 {len(self.generated_repositories)} 个Repository")
    
    async def stop_all_repositories(self) -> None:
        """停止所有Repository"""
        for repo in self.generated_repositories.values():
            await repo.stop()
        
        logger.info("所有Repository已停止")
    
    def generate_repository_documentation(self) -> str:
        """生成Repository文档"""
        doc_lines = ["# Auto-Generated Repositories\n"]
        
        for collection_name, repo in self.generated_repositories.items():
            doc_lines.append(f"## {collection_name.title()}Repository\n")
            
            # 获取Document类
            document_class = repo.document_class
            concurrent_fields = get_concurrent_fields(document_class)
            
            doc_lines.append(f"**Collection**: `{collection_name}`")
            doc_lines.append(f"**Document Class**: `{document_class.__name__}`")
            doc_lines.append("")
            
            # 基础方法
            doc_lines.append("### 基础方法")
            doc_lines.append("- `get(entity_id: str) -> Optional[T]`: 获取实体")
            doc_lines.append("- `create(entity_data: Dict) -> Optional[T]`: 创建实体")
            doc_lines.append("- `create_entity(**kwargs) -> Optional[T]`: 创建实体(使用关键字参数)")
            doc_lines.append("")
            
            # 并发操作方法
            if concurrent_fields:
                doc_lines.append("### 并发操作方法")
                for field_name, field_config in concurrent_fields.items():
                    operations = field_config.get("operations", [])
                    field_type = field_config.get("type", "any")
                    description = field_config.get("description", "")
                    
                    doc_lines.append(f"#### {field_name} ({field_type})")
                    if description:
                        doc_lines.append(f"*{description}*")
                    
                    if "incr" in operations:
                        doc_lines.append(f"- `add_{field_name}(entity_id, amount, source, reason)`: 增加{field_name}")
                    
                    if "decr" in operations:
                        doc_lines.append(f"- `consume_{field_name}(entity_id, amount, source, reason)`: 消耗{field_name}")
                    
                    if "set" in operations:
                        doc_lines.append(f"- `set_{field_name}(entity_id, value, source, reason)`: 设置{field_name}")
                    
                    doc_lines.append("")
            
            doc_lines.append("---\n")
        
        return "\n".join(doc_lines)
    
    def save_repository_documentation(self, output_path: str = "doc/repositories.md") -> None:
        """保存Repository文档到文件"""
        try:
            doc_content = self.generate_repository_documentation()
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(doc_content)
            
            logger.info(f"Repository文档已保存到: {output_path}")
            
        except Exception as e:
            logger.error(f"保存Repository文档失败: {e}")


class RepositoryManager:
    """Repository管理器"""
    
    def __init__(self, redis_client: RedisCache, mongo_client: MongoClient):
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self.generator = RepositoryGenerator(redis_client, mongo_client)
        self.repositories: Dict[str, BaseRepository] = {}
        self._started = False
    
    async def initialize(self, operation_logger) -> None:
        """初始化所有Repository"""
        if self._started:
            return
        
        # 生成所有Repository
        self.repositories = self.generator.generate_all_repositories()
        
        # 启动所有Repository
        await self.generator.start_all_repositories(operation_logger)
        
        self._started = True
        logger.info("Repository管理器初始化完成")
    
    async def shutdown(self) -> None:
        """关闭所有Repository"""
        if not self._started:
            return
        
        await self.generator.stop_all_repositories()
        self._started = False
        logger.info("Repository管理器已关闭")
    
    def get_repository(self, collection_name: str) -> Optional[BaseRepository]:
        """获取Repository"""
        return self.repositories.get(collection_name)
    
    def get_player_repository(self):
        """获取玩家Repository(类型安全的便捷方法)"""
        from .repositories.player_repository import PlayerRepository
        repo = self.get_repository("players")
        if repo and isinstance(repo, BaseRepository):
            # 这里可以进行类型转换或直接返回
            return repo
        return None
    
    def list_repositories(self) -> List[str]:
        """列出所有Repository"""
        return list(self.repositories.keys())
    
    async def get_all_stats(self) -> Dict[str, Any]:
        """获取所有Repository的统计信息"""
        stats = {}
        
        for collection_name, repo in self.repositories.items():
            try:
                stats[collection_name] = await repo.get_stats()
            except Exception as e:
                stats[collection_name] = {"error": str(e)}
        
        return stats
    
    async def force_persistence_all(self) -> None:
        """强制持久化所有Repository"""
        for repo in self.repositories.values():
            try:
                await repo.force_persistence()
            except Exception as e:
                logger.error(f"强制持久化Repository失败: {e}")


# 全局Repository管理器实例
_repository_manager: Optional[RepositoryManager] = None


async def get_repository_manager(
    redis_client: RedisCache,
    mongo_client: MongoClient
) -> RepositoryManager:
    """获取全局Repository管理器实例"""
    global _repository_manager
    if _repository_manager is None:
        _repository_manager = RepositoryManager(redis_client, mongo_client)
    return _repository_manager


async def close_repository_manager() -> None:
    """关闭全局Repository管理器实例"""
    global _repository_manager
    if _repository_manager is not None:
        await _repository_manager.shutdown()
        _repository_manager = None