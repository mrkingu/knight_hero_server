"""
消息路由器模块
Message Router Module

作者: lx
日期: 2025-06-18
描述: 实现路由规则定义、一致性哈希、故障转移、路由缓存
"""
import hashlib
import time
from typing import Dict, List, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio

from common.protocol.core.base_request import BaseRequest


class RouteType(Enum):
    """路由类型枚举"""
    MESSAGE_ID = "message_id"      # 基于消息ID路由
    PLAYER_ID = "player_id"        # 基于玩家ID路由
    CUSTOM = "custom"              # 自定义路由


@dataclass
class ServiceInstance:
    """服务实例信息"""
    service_name: str
    instance_id: str
    address: str
    port: int
    weight: int = 1
    is_healthy: bool = True
    last_health_check: float = field(default_factory=time.time)
    
    @property
    def endpoint(self) -> str:
        """获取服务端点"""
        return f"{self.address}:{self.port}"


@dataclass
class RouteRule:
    """路由规则"""
    name: str
    route_type: RouteType
    condition: Any  # 路由条件 (消息ID范围、玩家ID规则等)
    target_service: str
    priority: int = 1
    enabled: bool = True


class ConsistentHash:
    """一致性哈希环"""
    
    def __init__(self, replica_count: int = 160):
        """
        初始化一致性哈希环
        
        Args:
            replica_count: 虚拟节点数量
        """
        self.replica_count = replica_count
        self.ring: Dict[int, ServiceInstance] = {}
        self.sorted_keys: List[int] = []
        
    def _hash(self, key: str) -> int:
        """计算哈希值"""
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    
    def add_instance(self, instance: ServiceInstance) -> None:
        """添加服务实例"""
        for i in range(self.replica_count):
            key = self._hash(f"{instance.endpoint}:{i}")
            self.ring[key] = instance
        
        self._update_sorted_keys()
    
    def remove_instance(self, instance: ServiceInstance) -> None:
        """移除服务实例"""
        for i in range(self.replica_count):
            key = self._hash(f"{instance.endpoint}:{i}")
            if key in self.ring:
                del self.ring[key]
        
        self._update_sorted_keys()
    
    def _update_sorted_keys(self) -> None:
        """更新排序的键列表"""
        self.sorted_keys = sorted(self.ring.keys())
    
    def get_instance(self, key: str) -> Optional[ServiceInstance]:
        """根据键获取服务实例"""
        if not self.ring:
            return None
        
        hash_key = self._hash(key)
        
        # 找到第一个大于等于hash_key的节点
        for ring_key in self.sorted_keys:
            if ring_key >= hash_key:
                return self.ring[ring_key]
        
        # 如果没找到，返回第一个节点(环形结构)
        return self.ring[self.sorted_keys[0]]


class RouteCache:
    """路由缓存"""
    
    def __init__(self, max_size: int = 10000, ttl: int = 300):
        """
        初始化路由缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存存活时间(秒)
        """
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, Tuple[str, float]] = {}  # key -> (service_name, timestamp)
        self.access_order: List[str] = []  # LRU访问顺序
    
    def get(self, key: str) -> Optional[str]:
        """获取缓存的路由结果"""
        if key not in self.cache:
            return None
        
        service_name, timestamp = self.cache[key]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            self._remove(key)
            return None
        
        # 更新访问顺序
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        
        return service_name
    
    def put(self, key: str, service_name: str) -> None:
        """缓存路由结果"""
        # 检查是否需要清理空间
        if len(self.cache) >= self.max_size and key not in self.cache:
            self._evict_lru()
        
        self.cache[key] = (service_name, time.time())
        
        # 更新访问顺序
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
    
    def _remove(self, key: str) -> None:
        """移除缓存条目"""
        if key in self.cache:
            del self.cache[key]
        if key in self.access_order:
            self.access_order.remove(key)
    
    def _evict_lru(self) -> None:
        """移除最少使用的缓存条目"""
        if self.access_order:
            lru_key = self.access_order[0]
            self._remove(lru_key)
    
    def clear_expired(self) -> int:
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        for key, (_, timestamp) in self.cache.items():
            if current_time - timestamp > self.ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            self._remove(key)
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        current_time = time.time()
        active_count = sum(
            1 for _, timestamp in self.cache.values()
            if current_time - timestamp <= self.ttl
        )
        
        return {
            'total_entries': len(self.cache),
            'active_entries': active_count,
            'max_size': self.max_size,
            'hit_rate': getattr(self, '_hit_count', 0) / max(getattr(self, '_request_count', 1), 1)
        }


class MessageRouter:
    """消息路由器"""
    
    # 预定义路由配置
    ROUTE_CONFIG = {
        (1000, 1999): "logic",     # 逻辑服务
        (2000, 2999): "chat",      # 聊天服务
        (3000, 3999): "fight",     # 战斗服务
        (9000, 9999): "gateway",   # 网关自处理
    }
    
    def __init__(self):
        """初始化消息路由器"""
        # 预编译路由表
        self._route_table: Dict[int, str] = self._compile_routes()
        
        # 服务实例管理
        self._service_instances: Dict[str, List[ServiceInstance]] = {}
        self._consistent_hash: Dict[str, ConsistentHash] = {}
        
        # 路由缓存
        self._route_cache = RouteCache()
        
        # 故障转移
        self._failed_instances: Set[str] = set()
        self._health_check_interval = 30  # 健康检查间隔(秒)
        
        # 统计信息
        self._stats = {
            'total_routes': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'failed_routes': 0,
            'health_checks': 0
        }
    
    def _compile_routes(self) -> Dict[int, str]:
        """预编译路由表"""
        route_table = {}
        
        for (start, end), service_name in self.ROUTE_CONFIG.items():
            for msg_id in range(start, end + 1):
                route_table[msg_id] = service_name
        
        return route_table
    
    async def route_message(self, msg: BaseRequest) -> Optional[ServiceInstance]:
        """
        路由消息到对应服务实例
        
        Args:
            msg: 请求消息
            
        Returns:
            目标服务实例，如果路由失败返回None
        """
        try:
            self._stats['total_routes'] += 1
            
            # 获取消息ID
            msg_id = getattr(msg, 'msg_id', None) or getattr(msg, 'MESSAGE_TYPE', 0)
            
            # 检查路由缓存
            cache_key = f"{msg_id}:{getattr(msg, 'player_id', '')}"
            cached_service = self._route_cache.get(cache_key)
            
            if cached_service:
                self._stats['cache_hits'] += 1
                return await self._select_instance(cached_service, msg.player_id or "")
            
            self._stats['cache_misses'] += 1
            
            # 根据消息ID查找服务
            service_name = self._route_table.get(msg_id)
            
            if not service_name:
                self._stats['failed_routes'] += 1
                raise ValueError(f"Unknown message id: {msg_id}")
            
            # 缓存路由结果
            self._route_cache.put(cache_key, service_name)
            
            # 选择服务实例
            instance = await self._select_instance(service_name, msg.player_id or "")
            return instance
            
        except Exception as e:
            self._stats['failed_routes'] += 1
            print(f"路由消息失败: {e}")
            return None
    
    async def _select_instance(self, service_name: str, player_id: str) -> Optional[ServiceInstance]:
        """
        使用一致性哈希选择服务实例
        
        Args:
            service_name: 服务名称
            player_id: 玩家ID(用于一致性哈希)
            
        Returns:
            选中的服务实例
        """
        if service_name not in self._consistent_hash:
            return None
        
        hash_ring = self._consistent_hash[service_name]
        
        # 使用玩家ID作为哈希键，确保同一玩家的请求路由到同一实例
        hash_key = player_id if player_id else str(time.time())
        
        instance = hash_ring.get_instance(hash_key)
        
        # 检查实例健康状态
        if instance and not instance.is_healthy:
            # 尝试故障转移
            return await self._failover(service_name, instance, hash_key)
        
        return instance
    
    async def _failover(self, service_name: str, failed_instance: ServiceInstance, hash_key: str) -> Optional[ServiceInstance]:
        """
        故障转移逻辑
        
        Args:
            service_name: 服务名称
            failed_instance: 失败的服务实例
            hash_key: 哈希键
            
        Returns:
            故障转移后的服务实例
        """
        # 标记实例为失败
        self._failed_instances.add(failed_instance.endpoint)
        
        # 从哈希环中移除失败实例
        hash_ring = self._consistent_hash[service_name]
        hash_ring.remove_instance(failed_instance)
        
        # 重新选择实例
        new_instance = hash_ring.get_instance(hash_key)
        
        if new_instance and new_instance.is_healthy:
            print(f"故障转移成功: {failed_instance.endpoint} -> {new_instance.endpoint}")
            return new_instance
        
        print(f"故障转移失败: 没有健康的 {service_name} 实例")
        return None
    
    def register_service_instance(self, instance: ServiceInstance) -> None:
        """注册服务实例"""
        service_name = instance.service_name
        
        # 添加到实例列表
        if service_name not in self._service_instances:
            self._service_instances[service_name] = []
            self._consistent_hash[service_name] = ConsistentHash()
        
        self._service_instances[service_name].append(instance)
        self._consistent_hash[service_name].add_instance(instance)
        
        print(f"注册服务实例: {service_name} -> {instance.endpoint}")
    
    def unregister_service_instance(self, instance: ServiceInstance) -> None:
        """注销服务实例"""
        service_name = instance.service_name
        
        if service_name in self._service_instances:
            instances = self._service_instances[service_name]
            instances = [inst for inst in instances if inst.endpoint != instance.endpoint]
            self._service_instances[service_name] = instances
            
            if service_name in self._consistent_hash:
                self._consistent_hash[service_name].remove_instance(instance)
        
        print(f"注销服务实例: {service_name} -> {instance.endpoint}")
    
    async def health_check(self) -> None:
        """健康检查任务"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._perform_health_check()
            except Exception as e:
                print(f"健康检查错误: {e}")
    
    async def _perform_health_check(self) -> None:
        """执行健康检查"""
        self._stats['health_checks'] += 1
        
        for service_name, instances in self._service_instances.items():
            for instance in instances:
                try:
                    # 这里可以集成实际的健康检查逻辑
                    # 暂时模拟检查逻辑
                    if instance.endpoint in self._failed_instances:
                        # 尝试恢复失败的实例
                        instance.is_healthy = await self._check_instance_health(instance)
                        if instance.is_healthy:
                            self._failed_instances.discard(instance.endpoint)
                            # 重新添加到哈希环
                            self._consistent_hash[service_name].add_instance(instance)
                            print(f"实例恢复健康: {instance.endpoint}")
                    
                    instance.last_health_check = time.time()
                    
                except Exception as e:
                    print(f"检查实例 {instance.endpoint} 健康状态失败: {e}")
                    instance.is_healthy = False
    
    async def _check_instance_health(self, instance: ServiceInstance) -> bool:
        """检查单个实例健康状态"""
        # 这里应该实现实际的健康检查逻辑
        # 例如: gRPC健康检查、HTTP探测等
        # 暂时返回True作为示例
        return True
    
    def get_route_stats(self) -> Dict[str, Any]:
        """获取路由统计信息"""
        # 清理过期缓存
        expired_count = self._route_cache.clear_expired()
        
        cache_stats = self._route_cache.get_stats()
        
        return {
            'routing': self._stats.copy(),
            'cache': cache_stats,
            'expired_cache_entries': expired_count,
            'service_instances': {
                service: len(instances) 
                for service, instances in self._service_instances.items()
            },
            'failed_instances': len(self._failed_instances)
        }
    
    def get_service_instances(self, service_name: str) -> List[ServiceInstance]:
        """获取指定服务的所有实例"""
        return self._service_instances.get(service_name, [])
    
    def clear_cache(self) -> None:
        """清空路由缓存"""
        self._route_cache = RouteCache()