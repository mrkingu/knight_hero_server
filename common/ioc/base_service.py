"""
服务基类
Base Service Class

作者: mrkingu
日期: 2025-06-20
描述: 所有IoC管理的服务都应继承的基类，提供统一的生命周期管理
"""

import logging
from abc import ABC
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """
    服务基类
    
    所有由IoC容器管理的服务都应该继承这个基类
    提供统一的生命周期管理和基础功能
    """
    
    def __init__(self):
        """初始化基础服务"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialized = False
        self._container = None
        self._dependencies_injected = False
        
        # 服务元信息
        self._service_name = getattr(self.__class__, '_service_name', self.__class__.__name__)
        self._service_type = getattr(self.__class__, '_service_type', 'service')
        self._is_singleton = getattr(self.__class__, '_is_singleton', True)
    
    async def initialize(self) -> None:
        """
        初始化服务
        
        子类可以重写此方法来实现自定义初始化逻辑
        """
        if self._initialized:
            return
        
        try:
            self.logger.info(f"Initializing service: {self._service_name}")
            
            # 执行自定义初始化
            await self.on_initialize()
            
            self._initialized = True
            self.logger.info(f"Service initialized successfully: {self._service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize service {self._service_name}: {e}")
            raise
    
    async def shutdown(self) -> None:
        """
        关闭服务
        
        子类可以重写此方法来实现自定义清理逻辑
        """
        if not self._initialized:
            return
        
        try:
            self.logger.info(f"Shutting down service: {self._service_name}")
            
            # 执行自定义清理
            await self.on_shutdown()
            
            self._initialized = False
            self.logger.info(f"Service shutdown successfully: {self._service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to shutdown service {self._service_name}: {e}")
            raise
    
    async def on_initialize(self) -> None:
        """
        自定义初始化逻辑
        
        子类应该重写此方法来实现具体的初始化逻辑
        """
        pass
    
    async def on_shutdown(self) -> None:
        """
        自定义清理逻辑
        
        子类应该重写此方法来实现具体的清理逻辑
        """
        pass
    
    def set_container(self, container) -> None:
        """
        设置IoC容器引用
        
        Args:
            container: IoC容器实例
        """
        self._container = container
    
    def get_service(self, service_name: str) -> Any:
        """
        从容器获取其他服务
        
        Args:
            service_name: 服务名称
            
        Returns:
            服务实例
        """
        if not self._container:
            raise RuntimeError(f"No container available for service {self._service_name}")
        
        return self._container.get_service(service_name)
    
    def is_initialized(self) -> bool:
        """
        检查服务是否已初始化
        
        Returns:
            是否已初始化
        """
        return self._initialized
    
    def get_service_name(self) -> str:
        """
        获取服务名称
        
        Returns:
            服务名称
        """
        return self._service_name
    
    def get_service_type(self) -> str:
        """
        获取服务类型
        
        Returns:
            服务类型
        """
        return self._service_type
    
    def is_singleton(self) -> bool:
        """
        检查是否是单例服务
        
        Returns:
            是否是单例
        """
        return self._is_singleton
    
    async def health_check(self) -> dict:
        """
        健康检查
        
        子类可以重写此方法来实现自定义健康检查逻辑
        
        Returns:
            健康检查结果
        """
        return {
            "service_name": self._service_name,
            "service_type": self._service_type,
            "initialized": self._initialized,
            "status": "healthy" if self._initialized else "initializing"
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.__class__.__name__}(name={self._service_name}, type={self._service_type})"
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return (f"{self.__class__.__name__}(name={self._service_name}, "
                f"type={self._service_type}, initialized={self._initialized})")


class ServiceMetadata:
    """
    服务元数据
    
    存储服务的注册信息和配置
    """
    
    def __init__(
        self,
        name: str,
        service_class: type,
        service_type: str = "service",
        singleton: bool = True,
        lazy: bool = False,
        dependencies: Optional[list] = None
    ):
        self.name = name
        self.service_class = service_class
        self.service_type = service_type
        self.singleton = singleton
        self.lazy = lazy
        self.dependencies = dependencies or []
        self.instance = None
        self.initialized = False
    
    def __str__(self) -> str:
        return f"ServiceMetadata(name={self.name}, type={self.service_type})"