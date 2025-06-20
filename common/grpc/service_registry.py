"""
服务注册中心
自动管理服务地址和端口
作者: lx
日期: 2025-06-20
"""
from typing import Dict, List, Tuple, Optional
from enum import Enum
import os
import random

class ServiceType(Enum):
    """服务类型枚举"""
    GATEWAY = "gateway"
    LOGIC = "logic"
    CHAT = "chat"
    FIGHT = "fight"

class ServiceRegistry:
    """服务注册中心"""
    
    # 默认服务配置
    _default_services: Dict[ServiceType, List[Tuple[str, int]]] = {
        ServiceType.LOGIC: [
            ("localhost", 9001),
            ("localhost", 9002),
        ],
        ServiceType.CHAT: [
            ("localhost", 9101),
            ("localhost", 9102),
        ],
        ServiceType.FIGHT: [
            ("localhost", 9201),
            ("localhost", 9202),
        ],
        ServiceType.GATEWAY: [
            ("localhost", 8001),
            ("localhost", 8002),
        ]
    }
    
    def __init__(self):
        self._services: Dict[ServiceType, List[Tuple[str, int]]] = {}
        self._load_from_config()
    
    def _load_from_config(self):
        """从配置文件或环境变量加载服务地址"""
        # 优先从环境变量加载
        for service_type in ServiceType:
            env_key = f"{service_type.value.upper()}_SERVICES"
            env_value = os.getenv(env_key)
            
            if env_value:
                # 格式: "host1:port1,host2:port2"
                try:
                    addresses = []
                    for addr_str in env_value.split(','):
                        host, port = addr_str.strip().split(':')
                        addresses.append((host, int(port)))
                    self._services[service_type] = addresses
                except (ValueError, IndexError):
                    # 如果环境变量格式错误，使用默认配置
                    self._services[service_type] = self._default_services.get(service_type, [])
            else:
                # 使用默认配置
                self._services[service_type] = self._default_services.get(service_type, [])
    
    def get_service_addresses(self, service_type: ServiceType) -> List[Tuple[str, int]]:
        """
        获取服务地址列表
        
        Args:
            service_type: 服务类型
            
        Returns:
            地址列表 [(host, port), ...]
        """
        return self._services.get(service_type, [])
    
    def get_random_address(self, service_type: ServiceType) -> Optional[Tuple[str, int]]:
        """
        随机获取一个服务地址（负载均衡）
        
        Args:
            service_type: 服务类型
            
        Returns:
            随机选择的地址 (host, port) 或 None
        """
        addresses = self.get_service_addresses(service_type)
        if not addresses:
            return None
        return random.choice(addresses)
    
    def register_service(self, service_type: ServiceType, host: str, port: int):
        """
        注册服务地址
        
        Args:
            service_type: 服务类型
            host: 主机地址
            port: 端口号
        """
        if service_type not in self._services:
            self._services[service_type] = []
        
        address = (host, port)
        if address not in self._services[service_type]:
            self._services[service_type].append(address)
    
    def unregister_service(self, service_type: ServiceType, host: str, port: int):
        """
        注销服务地址
        
        Args:
            service_type: 服务类型
            host: 主机地址
            port: 端口号
        """
        if service_type in self._services:
            address = (host, port)
            if address in self._services[service_type]:
                self._services[service_type].remove(address)
    
    def get_service_count(self, service_type: ServiceType) -> int:
        """
        获取服务实例数量
        
        Args:
            service_type: 服务类型
            
        Returns:
            实例数量
        """
        return len(self._services.get(service_type, []))
    
    def health_check(self, service_type: ServiceType) -> Dict[Tuple[str, int], bool]:
        """
        健康检查（简单版本，实际项目中需要真正的健康检查）
        
        Args:
            service_type: 服务类型
            
        Returns:
            健康状态字典 {(host, port): is_healthy}
        """
        addresses = self.get_service_addresses(service_type)
        # 这里简化为都返回健康状态，实际应该进行真正的健康检查
        return {addr: True for addr in addresses}
    
    def get_all_services(self) -> Dict[ServiceType, List[Tuple[str, int]]]:
        """获取所有服务配置"""
        return self._services.copy()

# 全局服务注册中心实例
_global_registry: Optional[ServiceRegistry] = None

def get_service_registry() -> ServiceRegistry:
    """获取全局服务注册中心实例"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
    return _global_registry

__all__ = ['ServiceType', 'ServiceRegistry', 'get_service_registry']