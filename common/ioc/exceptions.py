"""
IoC异常定义
IoC Exception Definitions

作者: mrkingu
日期: 2025-06-20
描述: 定义IoC容器相关的异常类
"""


class IoCException(Exception):
    """IoC容器基础异常"""
    pass


class ServiceNotFoundException(IoCException):
    """服务未找到异常"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Service not found: {service_name}")


class DependencyResolutionException(IoCException):
    """依赖解析异常"""
    
    def __init__(self, service_name: str, dependency_name: str, reason: str = ""):
        self.service_name = service_name
        self.dependency_name = dependency_name
        self.reason = reason
        message = f"Failed to resolve dependency '{dependency_name}' for service '{service_name}'"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class CircularDependencyException(IoCException):
    """循环依赖异常"""
    
    def __init__(self, dependency_chain: list):
        self.dependency_chain = dependency_chain
        chain_str = " -> ".join(dependency_chain)
        super().__init__(f"Circular dependency detected: {chain_str}")


class ServiceRegistrationException(IoCException):
    """服务注册异常"""
    
    def __init__(self, service_name: str, reason: str):
        self.service_name = service_name
        self.reason = reason
        super().__init__(f"Failed to register service '{service_name}': {reason}")


class ServiceInitializationException(IoCException):
    """服务初始化异常"""
    
    def __init__(self, service_name: str, reason: str):
        self.service_name = service_name  
        self.reason = reason
        super().__init__(f"Failed to initialize service '{service_name}': {reason}")


class ContainerException(IoCException):
    """容器异常"""
    pass