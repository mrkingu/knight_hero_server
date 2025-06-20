"""
IoC容器框架
IoC Container Framework

作者: mrkingu  
日期: 2025-06-20
描述: 提供自动装载和依赖注入功能，类似Spring Boot的IoC容器机制
"""

from .decorators import service, repository, autowired, lazy, singleton, transactional
from .base_service import BaseService
from .container import ServiceContainer
from .service_scanner import ServiceScanner
from .exceptions import (
    IoCException, ServiceNotFoundException, DependencyResolutionException,
    CircularDependencyException, ServiceRegistrationException
)

__all__ = [
    # 装饰器
    'service',
    'repository', 
    'autowired',
    'lazy',
    'singleton',
    'transactional',
    
    # 核心类
    'BaseService',
    'ServiceContainer',
    'ServiceScanner',
    
    # 异常
    'IoCException',
    'ServiceNotFoundException',
    'DependencyResolutionException', 
    'CircularDependencyException',
    'ServiceRegistrationException',
]