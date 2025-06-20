"""
IoC装饰器实现
IoC Decorators Implementation

作者: mrkingu
日期: 2025-06-20
描述: 提供@service, @repository, @autowired等装饰器，支持自动装载和依赖注入
"""

import inspect
import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, Union

logger = logging.getLogger(__name__)

# 全局服务注册表
_service_registry: Dict[str, Dict[str, Any]] = {}
_dependency_registry: Dict[str, Dict[str, Any]] = {}


def service(name: Optional[str] = None, singleton: bool = True):
    """
    服务装饰器 - 标记业务服务类
    
    Args:
        name: 服务名称，如果不提供则使用类名
        singleton: 是否单例模式，默认True
        
    使用示例:
        @service("PlayerService")
        class PlayerService(BaseLogicService):
            pass
    """
    def decorator(cls: Type) -> Type:
        service_name = name or cls.__name__
        
        # 注册服务
        _service_registry[service_name] = {
            'class': cls,
            'type': 'service',
            'singleton': singleton,
            'instance': None,
            'initialized': False,
            'dependencies': []
        }
        
        # 添加服务名称属性
        cls._service_name = service_name
        cls._service_type = 'service'
        cls._is_singleton = singleton
        
        logger.debug(f"Registered service: {service_name}")
        return cls
    
    return decorator


def repository(name: Optional[str] = None, singleton: bool = True):
    """
    数据仓库装饰器 - 标记数据访问层类
    
    Args:
        name: 仓库名称，如果不提供则使用类名
        singleton: 是否单例模式，默认True
        
    使用示例:
        @repository("PlayerRepository")
        class PlayerRepository(BaseRepository):
            pass
    """
    def decorator(cls: Type) -> Type:
        repo_name = name or cls.__name__
        
        # 注册仓库
        _service_registry[repo_name] = {
            'class': cls,
            'type': 'repository',
            'singleton': singleton,
            'instance': None,
            'initialized': False,
            'dependencies': []
        }
        
        # 添加仓库名称属性
        cls._service_name = repo_name
        cls._service_type = 'repository'
        cls._is_singleton = singleton
        
        logger.debug(f"Registered repository: {repo_name}")
        return cls
    
    return decorator


def autowired(name: Optional[str] = None, required: bool = True, lazy: bool = False):
    """
    自动注入装饰器 - 用于属性和方法
    
    Args:
        name: 依赖服务名称，如果不提供则从方法名推断
        required: 是否必需依赖，默认True
        lazy: 是否延迟加载，默认False
        
    使用示例:
        @autowired("PlayerRepository")
        def player_repository(self):
            pass
    """
    def decorator(func_or_method: Callable) -> Callable:
        dependency_name = name
        
        # 如果是方法装饰器，从方法名推断依赖名称
        if not dependency_name:
            method_name = func_or_method.__name__
            # 移除 get_ 前缀，首字母大写
            if method_name.startswith('get_'):
                dependency_name = method_name[4:]
            else:
                dependency_name = method_name
            
            # 转换为PascalCase
            if dependency_name:
                dependency_name = ''.join(word.capitalize() for word in dependency_name.split('_'))
        
        # 创建属性装饰器
        def property_getter(self):
            # 从容器获取依赖
            container = getattr(self, '_container', None)
            if not container:
                raise RuntimeError(f"No container available for dependency injection: {dependency_name}")
            
            try:
                return container.get_service(dependency_name)
            except Exception as e:
                if required:
                    raise RuntimeError(f"Failed to inject required dependency '{dependency_name}': {e}")
                return None
        
        # 记录依赖信息
        property_getter._dependency_name = dependency_name
        property_getter._dependency_required = required
        property_getter._dependency_lazy = lazy
        
        # 返回属性
        return property(property_getter)
    
    return decorator


def lazy(func: Callable) -> Callable:
    """
    延迟加载装饰器
    
    使用示例:
        @lazy
        @autowired("ExpensiveService")
        def expensive_service(self):
            pass
    """
    # 标记为延迟加载
    func._is_lazy = True
    return func


def singleton(cls: Type) -> Type:
    """
    单例装饰器 - 确保类为单例模式
    
    使用示例:
        @singleton
        class ConfigService:
            pass
    """
    cls._is_singleton = True
    return cls


def transactional(rollback_for: tuple = (Exception,), propagation: str = "REQUIRED"):
    """
    事务装饰器 - 为方法添加事务支持
    
    Args:
        rollback_for: 触发回滚的异常类型
        propagation: 事务传播行为
        
    使用示例:
        @transactional()
        async def update_player_data(self, player_id: str, data: dict):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # 简化的事务实现，实际项目中需要集成具体的事务管理器
            transaction_manager = getattr(self, '_transaction_manager', None)
            
            if transaction_manager:
                try:
                    async with transaction_manager.begin():
                        return await func(self, *args, **kwargs)
                except rollback_for as e:
                    # 事务会自动回滚
                    raise e
            else:
                # 如果没有事务管理器，直接执行
                return await func(self, *args, **kwargs)
        
        wrapper._is_transactional = True
        wrapper._rollback_for = rollback_for
        wrapper._propagation = propagation
        
        return wrapper
    
    return decorator


def get_registered_services() -> Dict[str, Dict[str, Any]]:
    """获取所有已注册的服务"""
    return _service_registry.copy()


def clear_registry():
    """清空注册表（主要用于测试）"""
    global _service_registry, _dependency_registry
    _service_registry.clear()
    _dependency_registry.clear()


def scan_dependencies(cls: Type) -> list:
    """
    扫描类的依赖关系
    
    Args:
        cls: 要扫描的类
        
    Returns:
        依赖列表
    """
    dependencies = []
    
    # 扫描类的属性和方法
    for attr_name in dir(cls):
        if attr_name.startswith('_'):
            continue
            
        attr = getattr(cls, attr_name)
        
        # 检查是否是带有依赖信息的属性
        if hasattr(attr, 'fget') and hasattr(attr.fget, '_dependency_name'):
            dependency_info = {
                'name': attr.fget._dependency_name,
                'required': getattr(attr.fget, '_dependency_required', True),
                'lazy': getattr(attr.fget, '_dependency_lazy', False),
                'property_name': attr_name
            }
            dependencies.append(dependency_info)
    
    return dependencies