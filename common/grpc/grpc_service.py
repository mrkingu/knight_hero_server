"""
gRPC服务装饰器模块
gRPC Service Decorators Module

作者: lx
日期: 2025-06-18
描述: 提供@grpc_service和@grpc_method装饰器，用于自动注册RPC方法和服务
"""
import asyncio
import logging
import inspect
import time
from typing import Dict, List, Any, Callable, Optional, Type, Union
from functools import wraps
from dataclasses import dataclass, field
import grpc
from grpc import aio

from .protos import service_pb2, service_pb2_grpc
import orjson


logger = logging.getLogger(__name__)


@dataclass
class MethodInfo:
    """RPC方法信息"""
    name: str
    func: Callable
    service_name: str
    is_async: bool = True
    timeout: float = 3.0
    retry_count: int = 3
    description: str = ""
    
    # 统计信息
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_time: float = 0.0
    last_called: float = 0.0


@dataclass
class ServiceInfo:
    """RPC服务信息"""
    name: str
    cls: Type
    methods: Dict[str, MethodInfo] = field(default_factory=dict)
    instance: Optional[Any] = None
    address: str = ""
    port: int = 0
    
    # 拦截器
    interceptors: List[Callable] = field(default_factory=list)
    
    # 统计信息
    total_requests: int = 0
    active_requests: int = 0
    error_requests: int = 0


class RpcServiceRegistry:
    """RPC服务注册表"""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.method_mapping: Dict[str, MethodInfo] = {}
        
    def register_service(self, service_info: ServiceInfo) -> None:
        """注册服务"""
        self.services[service_info.name] = service_info
        
        # 注册方法映射
        for method_name, method_info in service_info.methods.items():
            full_method_name = f"{service_info.name}.{method_name}"
            self.method_mapping[full_method_name] = method_info
            
        logger.info(f"注册gRPC服务: {service_info.name} (方法数: {len(service_info.methods)})")
    
    def get_service(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        return self.services.get(service_name)
    
    def get_method(self, service_name: str, method_name: str) -> Optional[MethodInfo]:
        """获取方法信息"""
        full_method_name = f"{service_name}.{method_name}"
        if full_method_name in self.method_mapping:
            return self.method_mapping[full_method_name]
        
        # 如果完整名称没找到，尝试从服务中直接查找
        service_info = self.get_service(service_name)
        if service_info and method_name in service_info.methods:
            return service_info.methods[method_name]
        
        return None
    
    def list_services(self) -> List[str]:
        """列出所有服务名称"""
        return list(self.services.keys())
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_services": len(self.services),
            "total_methods": len(self.method_mapping),
            "services": {
                name: {
                    "methods": len(info.methods),
                    "total_requests": info.total_requests,
                    "active_requests": info.active_requests,
                    "error_requests": info.error_requests,
                    "methods_detail": {
                        method_name: {
                            "call_count": method.call_count,
                            "success_count": method.success_count,
                            "error_count": method.error_count,
                            "avg_time_ms": (method.total_time / method.call_count * 1000) if method.call_count > 0 else 0,
                            "last_called": method.last_called
                        }
                        for method_name, method in info.methods.items()
                    }
                }
                for name, info in self.services.items()
            }
        }


# 全局服务注册表
_registry = RpcServiceRegistry()


def grpc_service(service_name: str, address: str = "", port: int = 0) -> Callable:
    """
    gRPC服务装饰器
    
    用于标记一个类为gRPC服务，自动注册所有@grpc_method标记的方法
    
    Args:
        service_name: 服务名称
        address: 服务地址 (可选)
        port: 服务端口 (可选)
        
    使用示例:
        @grpc_service("logic")
        class LogicService:
            @grpc_method
            async def get_player_info(self, player_id: str) -> dict:
                return {"player_id": player_id, "level": 10}
    """
    def decorator(cls: Type) -> Type:
        # 创建服务信息
        service_info = ServiceInfo(
            name=service_name,
            cls=cls,
            address=address,
            port=port
        )
        
        # 扫描类中的RPC方法
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            
            # 检查是否有grpc_method标记
            if hasattr(attr, '_grpc_method_info'):
                method_info = attr._grpc_method_info
                method_info.service_name = service_name
                service_info.methods[attr_name] = method_info
                
                logger.debug(f"发现RPC方法: {service_name}.{attr_name}")
        
        # 注册服务
        _registry.register_service(service_info)
        
        # 给类添加服务信息
        cls._grpc_service_info = service_info
        
        return cls
    
    return decorator


def grpc_method(
    func: Optional[Callable] = None,
    *,
    timeout: float = 3.0,
    retry_count: int = 3,
    description: str = ""
) -> Union[Callable, Callable[[Callable], Callable]]:
    """
    gRPC方法装饰器
    
    用于标记一个方法为RPC方法，支持自动序列化、超时控制等
    
    Args:
        func: 被装饰的函数（当不带参数使用时）
        timeout: 超时时间(秒)
        retry_count: 重试次数
        description: 方法描述
        
    使用示例:
        @grpc_method
        async def get_player_info(self, player_id: str) -> dict:
            return {"player_id": player_id}
            
        @grpc_method(timeout=5.0, description="获取玩家信息")
        async def get_detailed_info(self, player_id: str) -> dict:
            return {"player_id": player_id}
    """
    def decorator(f: Callable) -> Callable:
        # 检查是否为异步方法
        is_async = inspect.iscoroutinefunction(f)
        
        # 创建方法信息
        method_info = MethodInfo(
            name=f.__name__,
            func=f,
            service_name="",  # 将在服务注册时设置
            is_async=is_async,
            timeout=timeout,
            retry_count=retry_count,
            description=description
        )
        
        @wraps(f)
        async def async_wrapper(self, *args, **kwargs):
            """异步方法包装器"""
            start_time = time.time()
            method_info.call_count += 1
            method_info.last_called = start_time
            
            try:
                # 执行原方法
                if is_async:
                    result = await f(self, *args, **kwargs)
                else:
                    result = f(self, *args, **kwargs)
                
                # 更新统计
                method_info.success_count += 1
                method_info.total_time += time.time() - start_time
                
                return result
                
            except Exception as e:
                method_info.error_count += 1
                logger.error(f"RPC方法执行失败 {method_info.service_name}.{method_info.name}: {e}")
                raise
        
        @wraps(f)
        def sync_wrapper(self, *args, **kwargs):
            """同步方法包装器"""
            start_time = time.time()
            method_info.call_count += 1
            method_info.last_called = start_time
            
            try:
                result = f(self, *args, **kwargs)
                method_info.success_count += 1
                method_info.total_time += time.time() - start_time
                return result
                
            except Exception as e:
                method_info.error_count += 1
                logger.error(f"RPC方法执行失败 {method_info.service_name}.{method_info.name}: {e}")
                raise
        
        # 根据是否异步返回不同的包装器
        wrapper = async_wrapper if is_async else sync_wrapper
        
        # 给包装器添加标记（这样才能在类扫描时找到）
        wrapper._grpc_method_info = method_info
        
        return wrapper
    
    # 如果func为None，说明装饰器是带参数调用的
    if func is None:
        return decorator
    else:
        # 如果func不为None，说明装饰器是不带参数调用的
        return decorator(func)


class GameServiceServicer(service_pb2_grpc.GameServiceServicer):
    """
    通用gRPC服务实现
    
    处理所有注册的RPC方法调用，自动路由到对应的服务实例
    """
    
    def __init__(self):
        self.interceptors: List[Callable] = []
        
    async def Call(
        self, 
        request: service_pb2.RpcRequest, 
        context: grpc.aio.ServicerContext
    ) -> service_pb2.RpcResponse:
        """
        处理单次RPC调用
        
        Args:
            request: RPC请求
            context: gRPC上下文
            
        Returns:
            RPC响应
        """
        service_name = request.service_name
        method_name = request.method_name
        
        logger.debug(f"收到RPC调用: {service_name}.{method_name}")
        
        # 初始化变量
        service_info = None
        
        try:
            # 执行拦截器 (请求前)
            for interceptor in self.interceptors:
                if asyncio.iscoroutinefunction(interceptor):
                    await interceptor(request, context, "before")
                else:
                    interceptor(request, context, "before")
            
            # 查找服务实例（先获取以便错误处理使用）
            service_info = _registry.get_service(service_name)
            if not service_info or not service_info.instance:
                raise ValueError(f"服务实例未找到: {service_name}")
            
            # 查找方法
            method_info = _registry.get_method(service_name, method_name)
            if not method_info:
                raise ValueError(f"未找到方法: {service_name}.{method_name}")
            
            # 更新服务统计
            service_info.total_requests += 1
            service_info.active_requests += 1
            
            try:
                # 反序列化参数
                if request.payload:
                    kwargs = orjson.loads(request.payload)
                else:
                    kwargs = {}
                
                # 调用方法
                if method_info.is_async:
                    result = await asyncio.wait_for(
                        method_info.func(service_info.instance, **kwargs),
                        timeout=method_info.timeout
                    )
                else:
                    result = method_info.func(service_info.instance, **kwargs)
                
                # 序列化结果
                response_payload = orjson.dumps(result) if result is not None else b""
                
                # 创建响应
                response = service_pb2.RpcResponse(
                    code=0,
                    message="success",
                    payload=response_payload
                )
                
                # 执行拦截器 (请求后)
                for interceptor in self.interceptors:
                    if asyncio.iscoroutinefunction(interceptor):
                        await interceptor(request, context, "after", response)
                    else:
                        interceptor(request, context, "after", response)
                
                logger.debug(f"RPC调用成功: {service_name}.{method_name}")
                return response
                
            finally:
                service_info.active_requests -= 1
            
        except asyncio.TimeoutError:
            service_info.error_requests += 1
            error_msg = f"RPC调用超时: {service_name}.{method_name}"
            logger.error(error_msg)
            return service_pb2.RpcResponse(
                code=504,
                message=error_msg,
                payload=b""
            )
            
        except Exception as e:
            # 安全地更新错误统计（如果service_info可用）
            if service_info:
                service_info.error_requests += 1
            
            error_msg = f"RPC调用失败: {service_name}.{method_name} - {str(e)}"
            logger.error(error_msg)
            return service_pb2.RpcResponse(
                code=500,
                message=error_msg,
                payload=b""
            )
    
    async def StreamCall(
        self,
        request_iterator,
        context: grpc.aio.ServicerContext
    ):
        """
        处理流式RPC调用
        
        Args:
            request_iterator: 请求流迭代器
            context: gRPC上下文
            
        Yields:
            RPC响应流
        """
        async for request in request_iterator:
            response = await self.Call(request, context)
            yield response
    
    def add_interceptor(self, interceptor: Callable) -> None:
        """添加请求拦截器"""
        self.interceptors.append(interceptor)
        logger.info(f"添加RPC拦截器: {interceptor.__name__}")


async def start_grpc_server(
    listen_addr: str = "localhost:50051",
    max_workers: int = 10
) -> grpc.aio.Server:
    """
    启动gRPC服务器
    
    Args:
        listen_addr: 监听地址 (host:port格式，如 "localhost:50051")
        max_workers: 最大工作线程数
        
    Returns:
        gRPC服务器实例
    """
    # 创建服务器
    server = grpc.aio.server()
    
    # 添加服务
    servicer = GameServiceServicer()
    service_pb2_grpc.add_GameServiceServicer_to_server(servicer, server)
    
    # 监听地址
    server.add_insecure_port(listen_addr)
    
    # 启动服务器
    await server.start()
    logger.info(f"gRPC服务器启动: {listen_addr}")
    
    return server


def register_service_instance(service_name: str, instance: Any) -> None:
    """
    注册服务实例
    
    Args:
        service_name: 服务名称
        instance: 服务实例对象
    """
    service_info = _registry.get_service(service_name)
    if service_info:
        service_info.instance = instance
        logger.info(f"注册服务实例: {service_name} -> {type(instance).__name__}")
    else:
        logger.error(f"服务未找到: {service_name}")


def get_service_registry() -> RpcServiceRegistry:
    """获取服务注册表"""
    return _registry


def get_service_stats() -> Dict:
    """获取服务统计信息"""
    return _registry.get_stats()