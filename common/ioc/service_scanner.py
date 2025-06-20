"""
服务扫描器
Service Scanner

作者: mrkingu
日期: 2025-06-20
描述: 自动扫描并注册服务和仓库
"""

import os
import sys
import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Set, Type

from .decorators import get_registered_services, scan_dependencies
from .base_service import ServiceMetadata
from .exceptions import ServiceRegistrationException

logger = logging.getLogger(__name__)


class ServiceScanner:
    """
    服务扫描器
    
    负责扫描指定目录下的Python模块，查找被装饰器标记的服务类
    """
    
    def __init__(self):
        self.scanned_services: Dict[str, ServiceMetadata] = {}
        self.scanned_paths: Set[str] = set()
    
    async def scan(self, scan_paths: List[str]) -> Dict[str, ServiceMetadata]:
        """
        扫描指定路径下的服务
        
        Args:
            scan_paths: 要扫描的路径列表
            
        Returns:
            发现的服务字典
        """
        logger.info(f"Starting service scan on paths: {scan_paths}")
        
        for path in scan_paths:
            await self._scan_path(path)
        
        # 从装饰器注册表获取服务信息
        self._collect_registered_services()
        
        logger.info(f"Service scan completed. Found {len(self.scanned_services)} services")
        return self.scanned_services
    
    async def _scan_path(self, scan_path: str) -> None:
        """
        扫描单个路径
        
        Args:
            scan_path: 要扫描的路径
        """
        if scan_path in self.scanned_paths:
            return
        
        self.scanned_paths.add(scan_path)
        
        try:
            # 转换为绝对路径
            abs_path = Path(scan_path).resolve()
            
            if not abs_path.exists():
                logger.warning(f"Scan path does not exist: {abs_path}")
                return
            
            if abs_path.is_file() and abs_path.suffix == '.py':
                # 扫描单个Python文件
                await self._scan_file(abs_path)
            elif abs_path.is_dir():
                # 递归扫描目录
                await self._scan_directory(abs_path)
            
        except Exception as e:
            logger.error(f"Error scanning path {scan_path}: {e}")
    
    async def _scan_directory(self, directory: Path) -> None:
        """
        递归扫描目录
        
        Args:
            directory: 要扫描的目录
        """
        logger.debug(f"Scanning directory: {directory}")
        
        try:
            for item in directory.iterdir():
                if item.is_file() and item.suffix == '.py' and not item.name.startswith('_'):
                    await self._scan_file(item)
                elif item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                    # 递归扫描子目录
                    await self._scan_directory(item)
        
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
    
    async def _scan_file(self, file_path: Path) -> None:
        """
        扫描单个Python文件
        
        Args:
            file_path: Python文件路径
        """
        logger.debug(f"Scanning file: {file_path}")
        
        try:
            # 构建模块路径
            module_path = self._file_to_module_path(file_path)
            if not module_path:
                return
            
            # 动态导入模块
            try:
                module = importlib.import_module(module_path)
                logger.debug(f"Successfully imported module: {module_path}")
            except ImportError as e:
                logger.debug(f"Could not import module {module_path}: {e}")
                return
            
            # 扫描模块中的类
            await self._scan_module(module)
            
        except Exception as e:
            logger.error(f"Error scanning file {file_path}: {e}")
    
    async def _scan_module(self, module) -> None:
        """
        扫描模块中的类
        
        Args:
            module: 已导入的模块
        """
        try:
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # 只扫描在当前模块中定义的类
                if obj.__module__ != module.__name__:
                    continue
                
                # 检查是否有服务相关的标记
                if hasattr(obj, '_service_name') and hasattr(obj, '_service_type'):
                    logger.debug(f"Found service class: {obj._service_name} ({name})")
        
        except Exception as e:
            logger.error(f"Error scanning module {module.__name__}: {e}")
    
    def _file_to_module_path(self, file_path: Path) -> str:
        """
        将文件路径转换为Python模块路径
        
        Args:
            file_path: 文件路径
            
        Returns:
            模块路径字符串
        """
        try:
            # 获取项目根目录（包含当前工作目录的路径）
            cwd = Path.cwd()
            
            # 尝试获取相对于当前工作目录的路径
            try:
                relative_path = file_path.relative_to(cwd)
            except ValueError:
                # 如果文件不在当前工作目录下，使用绝对路径
                logger.debug(f"File {file_path} is not relative to cwd {cwd}")
                return None
            
            # 移除.py后缀
            module_path = str(relative_path.with_suffix(''))
            
            # 将路径分隔符替换为点
            module_path = module_path.replace(os.sep, '.')
            
            return module_path
        
        except Exception as e:
            logger.error(f"Error converting file path to module path: {e}")
            return None
    
    def _collect_registered_services(self) -> None:
        """
        从装饰器注册表收集服务信息
        """
        registry = get_registered_services()
        
        for service_name, service_info in registry.items():
            try:
                # 扫描依赖关系
                dependencies = scan_dependencies(service_info['class'])
                
                # 创建服务元数据
                metadata = ServiceMetadata(
                    name=service_name,
                    service_class=service_info['class'],
                    service_type=service_info['type'],
                    singleton=service_info['singleton'],
                    dependencies=dependencies
                )
                
                self.scanned_services[service_name] = metadata
                logger.debug(f"Collected service metadata: {service_name}")
                
            except Exception as e:
                logger.error(f"Error collecting service metadata for {service_name}: {e}")
                raise ServiceRegistrationException(service_name, str(e))
    
    def get_services_by_type(self, service_type: str) -> Dict[str, ServiceMetadata]:
        """
        按类型获取服务
        
        Args:
            service_type: 服务类型 ('service', 'repository', 等)
            
        Returns:
            指定类型的服务字典
        """
        return {
            name: metadata 
            for name, metadata in self.scanned_services.items()
            if metadata.service_type == service_type
        }
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """
        获取依赖关系图
        
        Returns:
            依赖关系字典，key是服务名，value是它依赖的服务列表
        """
        dependency_graph = {}
        
        for service_name, metadata in self.scanned_services.items():
            dependencies = []
            for dep in metadata.dependencies:
                dependencies.append(dep['name'])
            dependency_graph[service_name] = dependencies
        
        return dependency_graph
    
    def clear(self) -> None:
        """清空扫描结果"""
        self.scanned_services.clear()
        self.scanned_paths.clear()