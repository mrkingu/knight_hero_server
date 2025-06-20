"""
gRPC连接池模块
gRPC Connection Pool Module

作者: lx  
日期: 2025-06-18
描述: 提供gRPC Channel连接池管理，支持健康检查、负载均衡和自动重连
"""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import grpc
# 简化健康检查，暂时不使用grpc_health


logger = logging.getLogger(__name__)


class ChannelState(Enum):
    """Channel连接状态枚举"""
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    TRANSIENT_FAILURE = "transient_failure"
    SHUTDOWN = "shutdown"


@dataclass
class ChannelInfo:
    """Channel信息"""
    channel: grpc.aio.Channel
    address: str
    state: ChannelState = ChannelState.IDLE
    last_health_check: float = field(default_factory=time.time)
    failure_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


class GrpcConnectionPool:
    """
    gRPC连接池管理器
    
    功能特性:
    1. 每个服务维护10-20个连接
    2. 健康检查(10秒间隔)
    3. 自动重连机制
    4. Round-Robin负载均衡
    5. 连接状态监控
    """
    
    def __init__(
        self,
        min_connections: int = 10,
        max_connections: int = 20,
        health_check_interval: int = 10,
        max_failures: int = 3,
        connection_timeout: int = 5
    ):
        """
        初始化连接池
        
        Args:
            min_connections: 最小连接数
            max_connections: 最大连接数  
            health_check_interval: 健康检查间隔(秒)
            max_failures: 最大失败次数
            connection_timeout: 连接超时时间(秒)
        """
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.health_check_interval = health_check_interval
        self.max_failures = max_failures
        self.connection_timeout = connection_timeout
        
        # 服务地址到连接池的映射
        self._pools: Dict[str, List[ChannelInfo]] = {}
        
        # Round-Robin索引
        self._round_robin_index: Dict[str, int] = {}
        
        # 健康检查任务
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        
        # 连接锁
        self._locks: Dict[str, asyncio.Lock] = {}
        
        # 统计信息
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "failed_connections": 0,
            "health_checks": 0,
            "reconnections": 0
        }
        
        logger.info(f"gRPC连接池初始化完成 - 连接范围: {min_connections}-{max_connections}")

    async def get_channel(self, service_address: str) -> Optional[grpc.aio.Channel]:
        """
        获取可用的gRPC Channel
        
        Args:
            service_address: 服务地址 (host:port)
            
        Returns:
            可用的Channel对象，如果无可用连接则返回None
        """
        # 确保连接池存在
        await self._ensure_pool_exists(service_address)
        
        # 获取连接池锁
        async with self._locks[service_address]:
            pool = self._pools[service_address]
            
            # 过滤健康的连接
            healthy_channels = [
                info for info in pool 
                if info.state == ChannelState.READY and info.failure_count < self.max_failures
            ]
            
            if not healthy_channels:
                logger.warning(f"服务 {service_address} 无健康连接可用")
                return None
            
            # Round-Robin负载均衡
            index = self._round_robin_index.get(service_address, 0)
            selected = healthy_channels[index % len(healthy_channels)]
            self._round_robin_index[service_address] = (index + 1) % len(healthy_channels)
            
            # 更新使用时间
            selected.last_used = time.time()
            
            logger.debug(f"选择连接: {service_address} - {selected.address}")
            return selected.channel

    async def _ensure_pool_exists(self, service_address: str) -> None:
        """确保指定服务的连接池存在"""
        if service_address not in self._pools:
            # 创建连接池
            self._pools[service_address] = []
            self._round_robin_index[service_address] = 0
            self._locks[service_address] = asyncio.Lock()
            
            # 创建初始连接
            await self._create_initial_connections(service_address)
            
            # 启动健康检查任务
            self._health_check_tasks[service_address] = asyncio.create_task(
                self._health_check_loop(service_address)
            )
            
            logger.info(f"为服务 {service_address} 创建连接池")

    async def _create_initial_connections(self, service_address: str) -> None:
        """为服务创建初始连接"""
        pool = self._pools[service_address]
        
        # 创建最小连接数
        for i in range(self.min_connections):
            try:
                channel = await self._create_channel(service_address)
                if channel:
                    channel_info = ChannelInfo(
                        channel=channel,
                        address=f"{service_address}#{i}",
                        state=ChannelState.READY
                    )
                    pool.append(channel_info)
                    self._stats["total_connections"] += 1
                    self._stats["active_connections"] += 1
                    
            except Exception as e:
                logger.error(f"创建初始连接失败 {service_address}#{i}: {e}")
                self._stats["failed_connections"] += 1

    async def _create_channel(self, service_address: str) -> Optional[grpc.aio.Channel]:
        """创建单个gRPC Channel"""
        try:
            # 创建Channel选项
            options = [
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.http2.min_time_between_pings_ms', 10000),
                ('grpc.http2.min_ping_interval_without_data_ms', 300000),
            ]
            
            # 创建异步Channel
            channel = grpc.aio.insecure_channel(service_address, options=options)
            
            # 测试连接
            await asyncio.wait_for(
                channel.channel_ready(),
                timeout=self.connection_timeout
            )
            
            logger.debug(f"成功创建连接: {service_address}")
            return channel
            
        except Exception as e:
            logger.error(f"创建连接失败 {service_address}: {e}")
            return None

    async def _health_check_loop(self, service_address: str) -> None:
        """健康检查循环"""
        while service_address in self._pools:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_check(service_address)
                
            except asyncio.CancelledError:
                logger.info(f"健康检查任务被取消: {service_address}")
                break
            except Exception as e:
                logger.error(f"健康检查异常 {service_address}: {e}")

    async def _perform_health_check(self, service_address: str) -> None:
        """执行健康检查"""
        if service_address not in self._pools:
            return
            
        async with self._locks[service_address]:
            pool = self._pools[service_address]
            
            for channel_info in pool:
                try:
                    # 简化健康检查：使用Channel的连接状态
                    state = channel_info.channel.get_state(try_to_connect=False)
                    
                    # 检查连接状态
                    if state == grpc.ChannelConnectivity.READY:
                        channel_info.state = ChannelState.READY
                        channel_info.failure_count = 0
                    elif state == grpc.ChannelConnectivity.IDLE:
                        # 尝试连接
                        await asyncio.wait_for(
                            channel_info.channel.channel_ready(),
                            timeout=3.0
                        )
                        channel_info.state = ChannelState.READY
                        channel_info.failure_count = 0
                    else:
                        channel_info.state = ChannelState.TRANSIENT_FAILURE
                        channel_info.failure_count += 1
                        
                    channel_info.last_health_check = time.time()
                    self._stats["health_checks"] += 1
                    
                except Exception as e:
                    # 健康检查失败
                    channel_info.state = ChannelState.TRANSIENT_FAILURE
                    channel_info.failure_count += 1
                    logger.warning(f"健康检查失败 {channel_info.address}: {e}")
                    
                    # 如果失败次数过多，尝试重连
                    if channel_info.failure_count >= self.max_failures:
                        await self._reconnect_channel(service_address, channel_info)

    async def _reconnect_channel(self, service_address: str, channel_info: ChannelInfo) -> None:
        """重连Channel"""
        try:
            # 关闭旧连接
            await channel_info.channel.close()
            
            # 创建新连接
            new_channel = await self._create_channel(service_address)
            if new_channel:
                channel_info.channel = new_channel
                channel_info.state = ChannelState.READY
                channel_info.failure_count = 0
                channel_info.last_health_check = time.time()
                
                self._stats["reconnections"] += 1
                logger.info(f"重连成功: {channel_info.address}")
            else:
                channel_info.state = ChannelState.TRANSIENT_FAILURE
                logger.error(f"重连失败: {channel_info.address}")
                
        except Exception as e:
            logger.error(f"重连异常 {channel_info.address}: {e}")
            channel_info.state = ChannelState.TRANSIENT_FAILURE

    async def close_pool(self, service_address: str) -> None:
        """关闭指定服务的连接池"""
        if service_address not in self._pools:
            return
            
        # 取消健康检查任务
        if service_address in self._health_check_tasks:
            self._health_check_tasks[service_address].cancel()
            del self._health_check_tasks[service_address]
            
        # 关闭所有连接
        async with self._locks[service_address]:
            pool = self._pools[service_address]
            for channel_info in pool:
                try:
                    await channel_info.channel.close()
                    channel_info.state = ChannelState.SHUTDOWN
                except Exception as e:
                    logger.error(f"关闭连接失败 {channel_info.address}: {e}")
                    
        # 清理资源
        del self._pools[service_address]
        del self._round_robin_index[service_address]
        del self._locks[service_address]
        
        logger.info(f"连接池已关闭: {service_address}")

    async def close_all(self) -> None:
        """关闭所有连接池"""
        service_addresses = list(self._pools.keys())
        
        for service_address in service_addresses:
            await self.close_pool(service_address)
            
        logger.info("所有连接池已关闭")

    def get_stats(self) -> Dict:
        """获取连接池统计信息"""
        pool_stats = {}
        
        for service_address, pool in self._pools.items():
            healthy_count = sum(
                1 for info in pool 
                if info.state == ChannelState.READY and info.failure_count < self.max_failures
            )
            
            pool_stats[service_address] = {
                "total_connections": len(pool),
                "healthy_connections": healthy_count,
                "failed_connections": sum(1 for info in pool if info.failure_count >= self.max_failures),
                "last_health_check": max(
                    (info.last_health_check for info in pool),
                    default=0
                )
            }
            
        return {
            "global_stats": self._stats,
            "pool_stats": pool_stats
        }


# 全局连接池实例
_global_pool: Optional[GrpcConnectionPool] = None


def get_connection_pool() -> GrpcConnectionPool:
    """获取全局连接池实例"""
    global _global_pool
    if _global_pool is None:
        _global_pool = GrpcConnectionPool()
    return _global_pool


async def close_global_pool() -> None:
    """关闭全局连接池"""
    global _global_pool
    if _global_pool:
        await _global_pool.close_all()
        _global_pool = None