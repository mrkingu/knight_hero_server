"""
连接池管理器模块
Connection Pool Manager Module

作者: lx
日期: 2025-06-18
描述: 负责WebSocket连接池的预分配、连接复用、并发连接统计、连接生命周期管理等
"""
import asyncio
import time
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from enum import Enum
from collections import deque
from fastapi import WebSocket

from .connection import Connection, ConnectionConfig, ConnectionState


class PoolState(Enum):
    """连接池状态枚举"""
    INITIALIZING = "initializing"  # 初始化中
    READY = "ready"               # 就绪
    DEGRADED = "degraded"         # 降级模式
    OVERLOADED = "overloaded"     # 过载
    SHUTDOWN = "shutdown"         # 关闭中


@dataclass
class ConnectionPoolConfig:
    """连接池配置"""
    # 连接池大小
    POOL_SIZE: int = 10000
    
    # 预分配配置
    PRE_ALLOCATE_SIZE: int = 1000    # 预分配连接数
    ALLOCATION_BATCH_SIZE: int = 100  # 批量分配大小
    
    # 清理配置
    CLEANUP_INTERVAL: int = 60       # 清理间隔（秒）
    MAX_IDLE_TIME: int = 300        # 最大空闲时间（秒）
    
    # 性能配置
    MAX_CONCURRENT_CONNECTIONS: int = 8000  # 最大并发连接数
    CONNECTION_TIMEOUT: int = 30     # 连接超时（秒）
    
    # 监控配置
    STATS_INTERVAL: int = 10         # 统计间隔（秒）


class ConnectionManager:
    """
    WebSocket连接池管理器
    
    提供高性能的连接池管理，支持10K+并发连接，连接预分配和复用，
    连接生命周期管理和性能监控
    """
    
    def __init__(self, config: Optional[ConnectionPoolConfig] = None):
        """
        初始化连接管理器
        
        Args:
            config: 连接池配置，默认使用标准配置
        """
        self.config = config or ConnectionPoolConfig()
        self.conn_config = ConnectionConfig()
        
        # 连接池状态
        self.state = PoolState.INITIALIZING
        self.created_at = time.time()
        
        # 连接存储
        self.active_connections: Dict[int, Connection] = {}      # 活跃连接
        self.idle_connections: deque[Connection] = deque()       # 空闲连接池
        self.connection_by_session: Dict[int, Connection] = {}   # 会话到连接映射
        
        # 统计信息
        self.total_created = 0           # 总创建连接数
        self.total_destroyed = 0         # 总销毁连接数
        self.peak_concurrent = 0         # 并发连接峰值
        self.connection_errors = 0       # 连接错误数
        self.pool_hits = 0              # 池命中次数
        self.pool_misses = 0            # 池未命中次数
        
        # 任务管理
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None
        self._prealloc_task: Optional[asyncio.Task] = None
        
        # 锁
        self._pool_lock = asyncio.Lock()
        self._stats_lock = asyncio.Lock()
        
        # 状态标志
        self._shutting_down = False
        self._initialized = False
    
    async def initialize(self) -> bool:
        """
        初始化连接池
        
        Returns:
            是否成功初始化
        """
        try:
            async with self._pool_lock:
                if self._initialized:
                    return True
                
                # 预分配连接对象
                await self._preallocate_connections()
                
                # 启动后台任务
                await self._start_background_tasks()
                
                self.state = PoolState.READY
                self._initialized = True
                
                return True
                
        except Exception as e:
            self.state = PoolState.DEGRADED
            self.connection_errors += 1
            return False
    
    async def shutdown(self) -> None:
        """关闭连接池"""
        self._shutting_down = True
        self.state = PoolState.SHUTDOWN
        
        # 停止后台任务
        await self._stop_background_tasks()
        
        # 关闭所有连接
        await self._close_all_connections()
        
        # 清理资源
        self.active_connections.clear()
        self.idle_connections.clear()
        self.connection_by_session.clear()
    
    async def create_connection(self, websocket: WebSocket) -> Optional[Connection]:
        """
        创建或获取连接对象
        
        Args:
            websocket: WebSocket对象
            
        Returns:
            连接对象，失败返回None
        """
        if self._shutting_down or self.state == PoolState.SHUTDOWN:
            return None
        
        # 检查并发限制
        if len(self.active_connections) >= self.config.MAX_CONCURRENT_CONNECTIONS:
            self.state = PoolState.OVERLOADED
            return None
        
        try:
            async with self._pool_lock:
                # 尝试从空闲池获取连接
                if self.idle_connections:
                    connection = self.idle_connections.popleft()
                    connection.websocket = websocket
                    connection.state = ConnectionState.IDLE
                    connection.created_at = time.time()
                    self.pool_hits += 1
                else:
                    # 创建新连接
                    connection = Connection(websocket, self.conn_config)
                    self.total_created += 1
                    self.pool_misses += 1
                
                # 接受连接
                if await connection.accept():
                    # 添加到活跃连接
                    self.active_connections[connection.id] = connection
                    
                    # 更新统计
                    current_count = len(self.active_connections)
                    if current_count > self.peak_concurrent:
                        self.peak_concurrent = current_count
                    
                    return connection
                else:
                    # 连接失败
                    self.connection_errors += 1
                    return None
                    
        except Exception as e:
            self.connection_errors += 1
            return None
    
    async def release_connection(self, connection: Connection) -> bool:
        """
        释放连接对象
        
        Args:
            connection: 要释放的连接对象
            
        Returns:
            是否成功释放
        """
        try:
            async with self._pool_lock:
                # 从活跃连接中移除
                if connection.id in self.active_connections:
                    del self.active_connections[connection.id]
                
                # 从会话映射中移除
                for session_id, conn in list(self.connection_by_session.items()):
                    if conn.id == connection.id:
                        del self.connection_by_session[session_id]
                
                # 关闭连接
                await connection.close()
                
                # 如果连接状态良好且池未满，回收到空闲池
                if (not self._shutting_down and 
                    connection.errors_count == 0 and 
                    len(self.idle_connections) < self.config.PRE_ALLOCATE_SIZE):
                    
                    # 重置连接状态
                    connection.websocket = None
                    connection.session = None
                    connection.state = ConnectionState.IDLE
                    connection._closed = False
                    connection._closing = False
                    
                    # 添加到空闲池
                    self.idle_connections.append(connection)
                else:
                    # 销毁连接
                    self.total_destroyed += 1
                
                return True
                
        except Exception as e:
            self.connection_errors += 1
            return False
    
    async def get_connection(self, connection_id: int) -> Optional[Connection]:
        """
        根据连接ID获取连接对象
        
        Args:
            connection_id: 连接ID
            
        Returns:
            连接对象，不存在返回None
        """
        return self.active_connections.get(connection_id)
    
    async def get_connection_by_session(self, session_id: int) -> Optional[Connection]:
        """
        根据会话ID获取连接对象
        
        Args:
            session_id: 会话ID
            
        Returns:
            连接对象，不存在返回None
        """
        return self.connection_by_session.get(session_id)
    
    async def bind_session(self, session_id: int, connection: Connection) -> bool:
        """
        绑定会话到连接
        
        Args:
            session_id: 会话ID
            connection: 连接对象
            
        Returns:
            是否成功绑定
        """
        try:
            async with self._pool_lock:
                self.connection_by_session[session_id] = connection
                return True
        except Exception:
            return False
    
    async def unbind_session(self, session_id: int) -> bool:
        """
        解绑会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            是否成功解绑
        """
        try:
            async with self._pool_lock:
                if session_id in self.connection_by_session:
                    del self.connection_by_session[session_id]
                return True
        except Exception:
            return False
    
    async def broadcast_message(self, message: Any, target_connections: Optional[Set[int]] = None) -> int:
        """
        广播消息到多个连接
        
        Args:
            message: 要广播的消息
            target_connections: 目标连接ID集合，None表示广播到所有连接
            
        Returns:
            成功发送的连接数
        """
        success_count = 0
        
        # 确定目标连接
        if target_connections is None:
            targets = list(self.active_connections.values())
        else:
            targets = [
                conn for conn_id, conn in self.active_connections.items()
                if conn_id in target_connections
            ]
        
        # 并发发送消息
        tasks = []
        for connection in targets:
            if connection.is_connected:
                if isinstance(message, dict):
                    task = connection.send_dict(message)
                else:
                    task = connection.send_text(str(message))
                tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)
        
        return success_count
    
    async def cleanup_expired_connections(self) -> int:
        """
        清理过期连接
        
        Returns:
            清理的连接数
        """
        cleaned_count = 0
        now = time.time()
        
        try:
            async with self._pool_lock:
                # 清理活跃连接中的无效连接
                expired_connections = []
                for connection in self.active_connections.values():
                    if (not connection.is_alive or 
                        (now - connection.last_activity) > self.config.MAX_IDLE_TIME):
                        expired_connections.append(connection)
                
                # 释放过期连接
                for connection in expired_connections:
                    await self.release_connection(connection)
                    cleaned_count += 1
                
                # 清理空闲池中的过期连接
                idle_to_remove = []
                for connection in self.idle_connections:
                    if (now - connection.created_at) > self.config.MAX_IDLE_TIME:
                        idle_to_remove.append(connection)
                
                for connection in idle_to_remove:
                    self.idle_connections.remove(connection)
                    self.total_destroyed += 1
                    cleaned_count += 1
        
        except Exception as e:
            self.connection_errors += 1
        
        return cleaned_count
    
    async def _preallocate_connections(self) -> None:
        """预分配连接对象"""
        try:
            for i in range(0, self.config.PRE_ALLOCATE_SIZE, self.config.ALLOCATION_BATCH_SIZE):
                batch_size = min(
                    self.config.ALLOCATION_BATCH_SIZE,
                    self.config.PRE_ALLOCATE_SIZE - i
                )
                
                # 批量创建空闲连接
                for _ in range(batch_size):
                    # 创建空连接对象（无WebSocket）
                    connection = Connection(None, self.conn_config)
                    connection.state = ConnectionState.IDLE
                    self.idle_connections.append(connection)
                
                # 避免阻塞事件循环
                await asyncio.sleep(0.001)
                
        except Exception as e:
            self.connection_errors += 1
    
    async def _cleanup_loop(self) -> None:
        """清理循环"""
        try:
            while not self._shutting_down:
                await asyncio.sleep(self.config.CLEANUP_INTERVAL)
                
                if not self._shutting_down:
                    cleaned = await self.cleanup_expired_connections()
                    if cleaned > 0:
                        print(f"清理了 {cleaned} 个过期连接")
                        
        except Exception as e:
            self.connection_errors += 1
    
    async def _stats_loop(self) -> None:
        """统计循环"""
        try:
            while not self._shutting_down:
                await asyncio.sleep(self.config.STATS_INTERVAL)
                
                if not self._shutting_down:
                    # 更新连接池状态
                    active_count = len(self.active_connections)
                    if active_count > self.config.MAX_CONCURRENT_CONNECTIONS * 0.9:
                        self.state = PoolState.OVERLOADED
                    elif active_count > self.config.MAX_CONCURRENT_CONNECTIONS * 0.7:
                        self.state = PoolState.DEGRADED
                    else:
                        self.state = PoolState.READY
                        
        except Exception as e:
            self.connection_errors += 1
    
    async def _start_background_tasks(self) -> None:
        """启动后台任务"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._stats_task = asyncio.create_task(self._stats_loop())
    
    async def _stop_background_tasks(self) -> None:
        """停止后台任务"""
        tasks = [
            task for task in [self._cleanup_task, self._stats_task, self._prealloc_task]
            if task and not task.done()
        ]
        
        if tasks:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _close_all_connections(self) -> None:
        """关闭所有连接"""
        try:
            # 关闭活跃连接
            close_tasks = []
            for connection in self.active_connections.values():
                close_tasks.append(connection.close())
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
            # 清理空闲连接
            while self.idle_connections:
                connection = self.idle_connections.popleft()
                self.total_destroyed += 1
                
        except Exception as e:
            self.connection_errors += 1
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """
        获取连接池统计信息
        
        Returns:
            统计信息字典
        """
        uptime = time.time() - self.created_at
        
        return {
            'pool_state': self.state.value,
            'uptime': uptime,
            'active_connections': len(self.active_connections),
            'idle_connections': len(self.idle_connections),
            'total_connections': len(self.active_connections) + len(self.idle_connections),
            'session_bindings': len(self.connection_by_session),
            'total_created': self.total_created,
            'total_destroyed': self.total_destroyed,
            'peak_concurrent': self.peak_concurrent,
            'connection_errors': self.connection_errors,
            'pool_hits': self.pool_hits,
            'pool_misses': self.pool_misses,
            'hit_rate': self.pool_hits / max(1, self.pool_hits + self.pool_misses),
            'config': {
                'pool_size': self.config.POOL_SIZE,
                'max_concurrent': self.config.MAX_CONCURRENT_CONNECTIONS,
                'pre_allocate_size': self.config.PRE_ALLOCATE_SIZE,
                'max_idle_time': self.config.MAX_IDLE_TIME
            }
        }
    
    def get_detailed_stats(self) -> Dict[str, Any]:
        """
        获取详细统计信息
        
        Returns:
            详细统计信息字典
        """
        stats = self.get_pool_stats()
        
        # 连接详细信息
        connection_details = []
        for connection in list(self.active_connections.values())[:10]:  # 只显示前10个
            connection_details.append(connection.get_stats())
        
        stats['connection_samples'] = connection_details
        
        # 性能指标
        if self.total_created > 0:
            stats['avg_connection_lifetime'] = (
                sum(conn.duration for conn in self.active_connections.values()) /
                len(self.active_connections) if self.active_connections else 0
            )
        
        return stats
    
    def __str__(self) -> str:
        """字符串表示"""
        return (f"ConnectionManager(state={self.state.value}, "
                f"active={len(self.active_connections)}, "
                f"idle={len(self.idle_connections)}, "
                f"peak={self.peak_concurrent})")
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()


# 全局连接管理器实例
_global_connection_manager: Optional[ConnectionManager] = None


async def get_connection_manager(config: Optional[ConnectionPoolConfig] = None) -> ConnectionManager:
    """
    获取全局连接管理器实例
    
    Args:
        config: 连接池配置
        
    Returns:
        连接管理器实例
    """
    global _global_connection_manager
    if _global_connection_manager is None:
        _global_connection_manager = ConnectionManager(config)
        await _global_connection_manager.initialize()
    return _global_connection_manager


async def close_connection_manager() -> None:
    """关闭全局连接管理器"""
    global _global_connection_manager
    if _global_connection_manager:
        await _global_connection_manager.shutdown()
        _global_connection_manager = None