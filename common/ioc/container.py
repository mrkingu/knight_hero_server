"""
IoC服务容器
IoC Service Container

作者: mrkingu
日期: 2025-06-20
描述: IoC容器核心实现，负责服务的注册、依赖注入和生命周期管理
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Type

from .base_service import BaseService, ServiceMetadata
from .service_scanner import ServiceScanner
from .exceptions import (
    ServiceNotFoundException, DependencyResolutionException,
    CircularDependencyException, ServiceInitializationException,
    ContainerException
)

logger = logging.getLogger(__name__)


class ServiceContainer:
    """
    IoC服务容器
    
    负责管理所有服务的生命周期，包括注册、创建、依赖注入和销毁
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceMetadata] = {}
        self.instances: Dict[str, Any] = {}
        self.scanner = ServiceScanner()
        self._initialized = False
        self._initializing = False
        self._initialization_order: List[str] = []
    
    async def initialize(self, scan_paths: Optional[List[str]] = None) -> None:
        """
        初始化容器
        
        Args:
            scan_paths: 要扫描的路径列表，如果为None则不扫描
        """
        if self._initialized or self._initializing:
            return
        
        self._initializing = True
        
        try:
            logger.info("Initializing IoC container...")
            
            # 1. 扫描服务（如果提供了扫描路径）
            if scan_paths:
                discovered_services = await self.scanner.scan(scan_paths)
                self.services.update(discovered_services)
                logger.info(f"Discovered {len(discovered_services)} services")
            
            # 2. 解析依赖关系并确定初始化顺序
            self._initialization_order = self._resolve_initialization_order()
            logger.info(f"Service initialization order: {self._initialization_order}")
            
            # 3. 按顺序初始化服务
            await self._initialize_services()
            
            self._initialized = True
            self._initializing = False
            
            logger.info(f"IoC container initialized successfully with {len(self.instances)} services")
            
        except Exception as e:
            self._initializing = False
            logger.error(f"Failed to initialize IoC container: {e}")
            raise ContainerException(f"Container initialization failed: {e}")
    
    async def shutdown(self) -> None:
        """关闭容器并清理所有服务"""
        if not self._initialized:
            return
        
        logger.info("Shutting down IoC container...")
        
        try:
            # 按相反顺序关闭服务
            shutdown_order = list(reversed(self._initialization_order))
            
            for service_name in shutdown_order:
                if service_name in self.instances:
                    try:
                        service_instance = self.instances[service_name]
                        if hasattr(service_instance, 'shutdown'):
                            await service_instance.shutdown()
                        logger.debug(f"Service shutdown: {service_name}")
                    except Exception as e:
                        logger.error(f"Error shutting down service {service_name}: {e}")
            
            # 清理容器状态
            self.instances.clear()
            self._initialized = False
            
            logger.info("IoC container shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during container shutdown: {e}")
            raise
    
    def register_service(self, metadata: ServiceMetadata) -> None:
        """
        手动注册服务
        
        Args:
            metadata: 服务元数据
        """
        if self._initialized:
            raise ContainerException("Cannot register services after container initialization")
        
        self.services[metadata.name] = metadata
        logger.debug(f"Manually registered service: {metadata.name}")
    
    def get_service(self, service_name: str) -> Any:
        """
        获取服务实例
        
        Args:
            service_name: 服务名称
            
        Returns:
            服务实例
        """
        if not self._initialized:
            raise ContainerException("Container not initialized")
        
        if service_name not in self.instances:
            raise ServiceNotFoundException(service_name)
        
        return self.instances[service_name]
    
    def has_service(self, service_name: str) -> bool:
        """
        检查是否存在指定服务
        
        Args:
            service_name: 服务名称
            
        Returns:
            是否存在
        """
        return service_name in self.instances
    
    def get_services_by_type(self, service_type: str) -> Dict[str, Any]:
        """
        按类型获取服务实例
        
        Args:
            service_type: 服务类型
            
        Returns:
            指定类型的服务实例字典
        """
        result = {}
        for name, metadata in self.services.items():
            if metadata.service_type == service_type and name in self.instances:
                result[name] = self.instances[name]
        return result
    
    async def _initialize_services(self) -> None:
        """按顺序初始化所有服务"""
        for service_name in self._initialization_order:
            if service_name not in self.services:
                continue
            
            try:
                await self._create_service_instance(service_name)
            except Exception as e:
                raise ServiceInitializationException(service_name, str(e))
    
    async def _create_service_instance(self, service_name: str) -> Any:
        """
        创建服务实例
        
        Args:
            service_name: 服务名称
            
        Returns:
            服务实例
        """
        if service_name in self.instances:
            return self.instances[service_name]
        
        metadata = self.services.get(service_name)
        if not metadata:
            raise ServiceNotFoundException(service_name)
        
        logger.debug(f"Creating service instance: {service_name}")
        
        try:
            # 1. 创建实例
            instance = metadata.service_class()
            
            # 2. 设置容器引用
            if hasattr(instance, 'set_container'):
                instance.set_container(self)
            
            # 3. 注入依赖
            await self._inject_dependencies(instance, metadata)
            
            # 4. 初始化服务
            if hasattr(instance, 'initialize'):
                await instance.initialize()
            
            # 5. 缓存实例（如果是单例）
            if metadata.singleton:
                self.instances[service_name] = instance
            
            logger.debug(f"Service instance created successfully: {service_name}")
            return instance
            
        except Exception as e:
            logger.error(f"Failed to create service instance {service_name}: {e}")
            raise ServiceInitializationException(service_name, str(e))
    
    async def _inject_dependencies(self, instance: Any, metadata: ServiceMetadata) -> None:
        """
        注入依赖
        
        Args:
            instance: 服务实例
            metadata: 服务元数据
        """
        for dependency in metadata.dependencies:
            dependency_name = dependency['name']
            
            try:
                # 获取依赖服务实例
                if dependency_name not in self.instances:
                    await self._create_service_instance(dependency_name)
                
                dependency_instance = self.instances[dependency_name]
                
                # 注入依赖（通过属性设置）
                property_name = dependency.get('property_name', dependency_name.lower())
                if hasattr(instance, f'_{property_name}'):
                    setattr(instance, f'_{property_name}', dependency_instance)
                
                logger.debug(f"Injected dependency {dependency_name} into {metadata.name}")
                
            except Exception as e:
                if dependency.get('required', True):
                    raise DependencyResolutionException(
                        metadata.name, dependency_name, str(e)
                    )
                else:
                    logger.warning(f"Optional dependency {dependency_name} not available for {metadata.name}")
    
    def _resolve_initialization_order(self) -> List[str]:
        """
        解析服务初始化顺序（拓扑排序）
        
        Returns:
            初始化顺序列表
        """
        # 构建依赖图
        dependency_graph = {}
        for service_name, metadata in self.services.items():
            dependencies = [dep['name'] for dep in metadata.dependencies]
            dependency_graph[service_name] = dependencies
        
        # 执行拓扑排序
        return self._topological_sort(dependency_graph)
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        """
        拓扑排序算法
        
        Args:
            graph: 依赖关系图，格式：{service: [dependencies]}
            
        Returns:
            排序后的服务列表
        """
        # 计算入度 - service A depends on service B means B -> A (B has outgoing edge to A)
        in_degree = {node: 0 for node in graph}
        
        # 构建正确的入度计算：如果A依赖B，那么A的入度+1
        for service, dependencies in graph.items():
            for dependency in dependencies:
                if dependency in in_degree:
                    in_degree[service] += 1  # service依赖dependency，所以service的入度+1
        
        # 找到所有入度为0的节点（没有依赖的节点）
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # 取出一个入度为0的节点
            current = queue.pop(0)
            result.append(current)
            
            # 更新依赖于当前节点的其他节点的入度
            for service, dependencies in graph.items():
                if current in dependencies and service not in result:
                    in_degree[service] -= 1
                    if in_degree[service] == 0:
                        queue.append(service)
        
        # 检查是否有循环依赖
        if len(result) != len(graph):
            # 找出参与循环依赖的节点
            remaining = [node for node in graph if node not in result]
            raise CircularDependencyException(remaining)
        
        return result
    
    def get_container_info(self) -> dict:
        """
        获取容器信息
        
        Returns:
            容器状态信息
        """
        return {
            'initialized': self._initialized,
            'total_services': len(self.services),
            'active_instances': len(self.instances),
            'initialization_order': self._initialization_order,
            'services': {
                name: {
                    'type': metadata.service_type,
                    'singleton': metadata.singleton,
                    'initialized': name in self.instances
                }
                for name, metadata in self.services.items()
            }
        }