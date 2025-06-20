"""
简化的gRPC装饰器
自动处理服务发现和负载均衡
作者: lx
日期: 2025-06-20
"""
import asyncio
import grpc
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type
from .service_registry import ServiceRegistry, ServiceType, get_service_registry

class GrpcServiceClient:
    """gRPC服务客户端基类"""
    
    def __init__(self, service_type: ServiceType):
        self._service_type = service_type
        self._registry = get_service_registry()
        self._clients: Dict[str, grpc.aio.Channel] = {}
        self._current_index = 0
    
    async def _get_channel(self) -> Optional[grpc.aio.Channel]:
        """获取gRPC通道（负载均衡）"""
        addresses = self._registry.get_service_addresses(self._service_type)
        if not addresses:
            return None
        
        # 简单的轮询负载均衡
        address = addresses[self._current_index % len(addresses)]
        self._current_index += 1
        
        address_key = f"{address[0]}:{address[1]}"
        
        if address_key not in self._clients:
            channel = grpc.aio.insecure_channel(address_key)
            self._clients[address_key] = channel
        
        return self._clients[address_key]
    
    async def close(self):
        """关闭所有客户端连接"""
        for channel in self._clients.values():
            await channel.close()
        self._clients.clear()

def grpc_service(service_type: ServiceType):
    """
    gRPC服务装饰器
    
    使用示例:
    @grpc_service(ServiceType.LOGIC)
    class UserService:
        async def get_user(self, user_id: str):
            pass
    """
    def decorator(cls: Type) -> Type:
        # 继承自GrpcServiceClient以获得客户端功能
        if not issubclass(cls, GrpcServiceClient):
            # 动态继承
            class WrappedClass(cls, GrpcServiceClient):
                def __init__(self, *args, **kwargs):
                    # 先初始化GrpcServiceClient
                    GrpcServiceClient.__init__(self, service_type)
                    # 再初始化原始类
                    if hasattr(cls, '__init__'):
                        cls.__init__(self, *args, **kwargs)
            
            WrappedClass.__name__ = cls.__name__
            WrappedClass.__qualname__ = cls.__qualname__
            return WrappedClass
        else:
            # 如果已经是子类，直接设置服务类型
            original_init = cls.__init__
            
            def new_init(self, *args, **kwargs):
                GrpcServiceClient.__init__(self, service_type)
                if original_init != object.__init__:
                    original_init(self, *args, **kwargs)
            
            cls.__init__ = new_init
            return cls
    
    return decorator

def grpc_method(
    method_name: Optional[str] = None,
    timeout: float = 30.0,
    retry_attempts: int = 3
):
    """
    gRPC方法装饰器
    
    使用示例:
    @grpc_method()
    async def get_user_info(self, user_id: str):
        pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            if not isinstance(self, GrpcServiceClient):
                raise RuntimeError("grpc_method can only be used on classes decorated with @grpc_service")
            
            # 获取方法名
            actual_method_name = method_name or func.__name__
            
            # 重试机制
            for attempt in range(retry_attempts):
                try:
                    # 获取gRPC通道
                    channel = await self._get_channel()
                    if not channel:
                        raise RuntimeError(f"No available services for {self._service_type}")
                    
                    # 这里简化处理，实际项目中需要根据具体的proto文件生成的stub
                    # 构建请求（简化版本）
                    request_data = self._build_request(actual_method_name, *args, **kwargs)
                    
                    # 调用远程方法（这里需要根据实际的proto服务接口实现）
                    response = await self._call_remote_method(channel, actual_method_name, request_data, timeout)
                    
                    # 解析响应
                    return self._parse_response(response)
                
                except grpc.aio.AioRpcError as e:
                    if attempt == retry_attempts - 1:
                        raise RuntimeError(f"gRPC call failed after {retry_attempts} attempts: {e}")
                    
                    # 等待后重试
                    await asyncio.sleep(0.5 * (attempt + 1))
                
                except Exception as e:
                    if attempt == retry_attempts - 1:
                        raise e
                    await asyncio.sleep(0.5 * (attempt + 1))
        
        return wrapper
    
    return decorator

# 为了向后兼容，保留原有的装饰器接口
def simple_grpc_client(service_name: str, address: str = None, port: int = None):
    """
    简化的gRPC客户端装饰器（向后兼容）
    
    Args:
        service_name: 服务名称
        address: 服务地址（可选，会自动从注册中心获取）
        port: 服务端口（可选，会自动从注册中心获取）
    """
    def decorator(cls: Type) -> Type:
        # 尝试从服务名称映射到ServiceType
        service_type_map = {
            'logic': ServiceType.LOGIC,
            'chat': ServiceType.CHAT,
            'fight': ServiceType.FIGHT,
            'gateway': ServiceType.GATEWAY
        }
        
        service_type = service_type_map.get(service_name.lower())
        if not service_type:
            # 如果无法映射，使用LOGIC作为默认值
            service_type = ServiceType.LOGIC
        
        # 如果提供了地址和端口，注册到服务中心
        if address and port:
            registry = get_service_registry()
            registry.register_service(service_type, address, port)
        
        # 应用grpc_service装饰器
        return grpc_service(service_type)(cls)
    
    return decorator

__all__ = [
    'GrpcServiceClient', 'grpc_service', 'grpc_method', 'simple_grpc_client'
]