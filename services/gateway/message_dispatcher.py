"""
消息分发器模块
Message Dispatcher Module

作者: lx
日期: 2025-06-18  
描述: 实现消息路由表管理、服务发现集成、批量分发、负载均衡
"""
import asyncio
import time
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
import logging

from common.protocol.core.base_request import BaseRequest
from common.grpc.grpc_client import GrpcClient
from common.grpc.grpc_pool import get_connection_pool
from .router import MessageRouter, ServiceInstance
from .message_queue import PriorityMessageQueue, QueuedMessage, MessagePriority


logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """批处理配置"""
    batch_size: int = 100           # 批次大小
    timeout_ms: int = 10            # 批处理超时(毫秒)
    max_batches: int = 10           # 最大并发批次数
    retry_delay_ms: int = 100       # 重试延迟(毫秒)


@dataclass
class DispatchResult:
    """分发结果"""
    success: bool
    message_id: str
    service_name: str
    instance_endpoint: str
    error: Optional[str] = None
    latency_ms: float = 0.0
    retry_count: int = 0


class BatchProcessor:
    """批量消息处理器"""
    
    def __init__(self, batch_config: BatchConfig):
        """
        初始化批处理器
        
        Args:
            batch_config: 批处理配置
        """
        self.config = batch_config
        self._buffer: List[QueuedMessage] = []
        self._timer_task: Optional[asyncio.Task] = None
        self._processing = False
        
        # 批处理回调
        self._batch_handler: Optional[Callable] = None
    
    def set_batch_handler(self, handler: Callable[[List[QueuedMessage]], None]) -> None:
        """设置批处理回调函数"""
        self._batch_handler = handler
    
    async def add_message(self, message: QueuedMessage) -> None:
        """
        添加消息到批处理缓冲
        
        Args:
            message: 待处理的消息
        """
        if self._processing:
            return
        
        self._buffer.append(message)
        
        # 检查是否达到批次大小
        if len(self._buffer) >= self.config.batch_size:
            await self._flush()
        elif not self._timer_task:
            # 启动超时定时器
            self._timer_task = asyncio.create_task(self._timeout_flush())
    
    async def _flush(self) -> None:
        """刷新缓冲区"""
        if not self._buffer or self._processing:
            return
        
        self._processing = True
        
        try:
            # 取出当前缓冲区内容
            batch = self._buffer.copy()
            self._buffer.clear()
            
            # 取消定时器
            if self._timer_task:
                self._timer_task.cancel()
                self._timer_task = None
            
            # 执行批处理
            if self._batch_handler:
                await self._batch_handler(batch)
                
        finally:
            self._processing = False
    
    async def _timeout_flush(self) -> None:
        """超时刷新"""
        try:
            await asyncio.sleep(self.config.timeout_ms / 1000.0)
            await self._flush()
        except asyncio.CancelledError:
            pass
    
    async def force_flush(self) -> None:
        """强制刷新"""
        await self._flush()
    
    def get_buffer_size(self) -> int:
        """获取缓冲区大小"""
        return len(self._buffer)


class ServiceDiscoveryIntegration:
    """服务发现集成"""
    
    def __init__(self, router: MessageRouter):
        """
        初始化服务发现集成
        
        Args:
            router: 消息路由器
        """
        self.router = router
        self._discovery_tasks: Set[asyncio.Task] = set()
        self._service_clients: Dict[str, GrpcClient] = {}
        
        # 服务发现配置
        self._discovery_interval = 30  # 发现间隔(秒)
        self._health_check_interval = 10  # 健康检查间隔(秒)
    
    async def start(self) -> None:
        """启动服务发现"""
        # 启动服务发现任务
        discovery_task = asyncio.create_task(self._discover_services())
        health_check_task = asyncio.create_task(self._health_check_loop())
        
        self._discovery_tasks.add(discovery_task)
        self._discovery_tasks.add(health_check_task)
        
        logger.info("服务发现已启动")
    
    async def stop(self) -> None:
        """停止服务发现"""
        # 取消所有任务
        for task in self._discovery_tasks:
            task.cancel()
        
        if self._discovery_tasks:
            await asyncio.gather(*self._discovery_tasks, return_exceptions=True)
        
        self._discovery_tasks.clear()
        
        # 关闭客户端连接
        for client in self._service_clients.values():
            await client.close()
        self._service_clients.clear()
        
        logger.info("服务发现已停止")
    
    async def _discover_services(self) -> None:
        """服务发现循环"""
        while True:
            try:
                await asyncio.sleep(self._discovery_interval)
                
                # 这里集成实际的服务发现系统 (Consul, etcd, Kubernetes等)
                # 暂时使用模拟数据
                await self._mock_service_discovery()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"服务发现错误: {e}")
    
    async def _mock_service_discovery(self) -> None:
        """模拟服务发现"""
        # 模拟发现的服务实例
        mock_services = [
            ServiceInstance("logic", "logic-1", "127.0.0.1", 50001, weight=1),
            ServiceInstance("logic", "logic-2", "127.0.0.1", 50002, weight=1),
            ServiceInstance("chat", "chat-1", "127.0.0.1", 50003, weight=1),
            ServiceInstance("fight", "fight-1", "127.0.0.1", 50004, weight=1),
        ]
        
        # 注册服务实例
        for instance in mock_services:
            self.router.register_service_instance(instance)
            
            # 创建gRPC客户端
            if instance.service_name not in self._service_clients:
                client = GrpcClient(f"{instance.address}:{instance.port}")
                self._service_clients[instance.service_name] = client
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._perform_health_checks()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查错误: {e}")
    
    async def _perform_health_checks(self) -> None:
        """执行健康检查"""
        for service_name, client in self._service_clients.items():
            try:
                # 执行gRPC健康检查
                result = await client.call("Health", "Check", {})
                
                # 更新服务实例健康状态
                instances = self.router.get_service_instances(service_name)
                for instance in instances:
                    instance.is_healthy = result.get("status") == "SERVING"
                    
            except Exception as e:
                logger.warning(f"服务 {service_name} 健康检查失败: {e}")
                
                # 标记所有实例为不健康
                instances = self.router.get_service_instances(service_name)
                for instance in instances:
                    instance.is_healthy = False
    
    def get_service_client(self, service_name: str) -> Optional[GrpcClient]:
        """获取服务客户端"""
        return self._service_clients.get(service_name)


class MessageDispatcher:
    """消息分发器"""
    
    def __init__(self, 
                 router: MessageRouter,
                 queue: PriorityMessageQueue,
                 batch_config: Optional[BatchConfig] = None):
        """
        初始化消息分发器
        
        Args:
            router: 消息路由器
            queue: 消息队列
            batch_config: 批处理配置
        """
        self.router = router
        self.queue = queue
        self.batch_config = batch_config or BatchConfig()
        
        # 服务发现集成
        self.service_discovery = ServiceDiscoveryIntegration(router)
        
        # 批处理器
        self._batch_processors: Dict[str, BatchProcessor] = {}
        
        # 分发统计
        self._dispatch_stats = {
            'total_dispatched': 0,
            'successful_dispatches': 0,
            'failed_dispatches': 0,
            'total_latency_ms': 0.0,
            'batch_count': 0,
            'retry_count': 0
        }
        
        # 分发任务
        self._dispatch_tasks: Set[asyncio.Task] = set()
        self._running = False
    
    async def start(self) -> None:
        """启动消息分发器"""
        if self._running:
            return
        
        self._running = True
        
        # 启动服务发现
        await self.service_discovery.start()
        
        # 启动分发循环
        dispatch_task = asyncio.create_task(self._dispatch_loop())
        self._dispatch_tasks.add(dispatch_task)
        
        logger.info("消息分发器已启动")
    
    async def stop(self) -> None:
        """停止消息分发器"""
        if not self._running:
            return
        
        self._running = False
        
        # 停止服务发现
        await self.service_discovery.stop()
        
        # 停止分发任务
        for task in self._dispatch_tasks:
            task.cancel()
        
        if self._dispatch_tasks:
            await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
        
        self._dispatch_tasks.clear()
        
        # 刷新所有批处理器
        for processor in self._batch_processors.values():
            await processor.force_flush()
        
        logger.info("消息分发器已停止")
    
    async def _dispatch_loop(self) -> None:
        """分发循环"""
        while self._running:
            try:
                # 从队列获取消息
                queued_message = await self.queue.dequeue(timeout=1.0)
                if not queued_message:
                    continue
                
                # 分发消息
                await self._dispatch_message(queued_message)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"分发循环错误: {e}")
    
    async def _dispatch_message(self, queued_message: QueuedMessage) -> None:
        """
        分发单个消息
        
        Args:
            queued_message: 待分发的消息
        """
        try:
            # 路由消息
            instance = await self.router.route_message(queued_message.message)
            if not instance:
                await self._handle_dispatch_failure(queued_message, "路由失败")
                return
            
            # 获取或创建批处理器
            service_name = instance.service_name
            processor = self._get_batch_processor(service_name)
            
            # 添加到批处理器
            await processor.add_message(queued_message)
            
        except Exception as e:
            await self._handle_dispatch_failure(queued_message, str(e))
    
    def _get_batch_processor(self, service_name: str) -> BatchProcessor:
        """获取或创建批处理器"""
        if service_name not in self._batch_processors:
            processor = BatchProcessor(self.batch_config)
            processor.set_batch_handler(
                lambda batch: self._process_batch(service_name, batch)
            )
            self._batch_processors[service_name] = processor
        
        return self._batch_processors[service_name]
    
    async def _process_batch(self, service_name: str, batch: List[QueuedMessage]) -> None:
        """
        处理消息批次
        
        Args:
            service_name: 目标服务名
            batch: 消息批次
        """
        if not batch:
            return
        
        start_time = time.time()
        self._dispatch_stats['batch_count'] += 1
        
        try:
            # 获取服务客户端
            client = self.service_discovery.get_service_client(service_name)
            if not client:
                for message in batch:
                    await self._handle_dispatch_failure(message, f"未找到服务客户端: {service_name}")
                return
            
            # 批量发送消息
            results = await self._send_batch(client, service_name, batch)
            
            # 处理结果
            for result in results:
                if result.success:
                    self._dispatch_stats['successful_dispatches'] += 1
                else:
                    self._dispatch_stats['failed_dispatches'] += 1
                    
                    # 查找对应的消息进行重试处理
                    for message in batch:
                        if message.message_id == result.message_id:
                            await self._handle_dispatch_failure(message, result.error)
                            break
            
            # 更新延迟统计
            latency_ms = (time.time() - start_time) * 1000
            self._dispatch_stats['total_latency_ms'] += latency_ms
            
        except Exception as e:
            logger.error(f"批处理失败: {e}")
            for message in batch:
                await self._handle_dispatch_failure(message, str(e))
    
    async def _send_batch(self, 
                         client: GrpcClient, 
                         service_name: str, 
                         batch: List[QueuedMessage]) -> List[DispatchResult]:
        """
        发送消息批次
        
        Args:
            client: gRPC客户端
            service_name: 服务名称
            batch: 消息批次
            
        Returns:
            分发结果列表
        """
        results = []
        
        for queued_message in batch:
            start_time = time.time()
            
            try:
                # 调用远程服务
                request_data = queued_message.message.to_dict()
                response = await client.call(
                    service_name.title(), 
                    "HandleMessage", 
                    request_data
                )
                
                latency_ms = (time.time() - start_time) * 1000
                
                result = DispatchResult(
                    success=True,
                    message_id=queued_message.message_id,
                    service_name=service_name,
                    instance_endpoint=client.address,
                    latency_ms=latency_ms,
                    retry_count=queued_message.retry_count
                )
                
                self._dispatch_stats['total_dispatched'] += 1
                
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                
                result = DispatchResult(
                    success=False,
                    message_id=queued_message.message_id,
                    service_name=service_name,
                    instance_endpoint=client.address,
                    error=str(e),
                    latency_ms=latency_ms,
                    retry_count=queued_message.retry_count
                )
                
                logger.warning(f"消息分发失败: {e}")
            
            results.append(result)
        
        return results
    
    async def _handle_dispatch_failure(self, 
                                     queued_message: QueuedMessage, 
                                     error: str) -> None:
        """
        处理分发失败
        
        Args:
            queued_message: 失败的消息
            error: 错误信息
        """
        logger.warning(f"消息分发失败: {error}, 消息ID: {queued_message.message_id}")
        
        # 尝试重试
        if queued_message.retry_count < queued_message.max_retries:
            success = await self.queue.retry_message(queued_message)
            if success:
                self._dispatch_stats['retry_count'] += 1
                logger.info(f"消息重试入队: {queued_message.message_id}, 重试次数: {queued_message.retry_count}")
            else:
                logger.error(f"消息重试失败: {queued_message.message_id}")
        else:
            logger.error(f"消息超过最大重试次数: {queued_message.message_id}")
    
    def get_dispatch_stats(self) -> Dict[str, Any]:
        """获取分发统计信息"""
        stats = self._dispatch_stats.copy()
        
        # 计算平均延迟
        if stats['successful_dispatches'] > 0:
            stats['avg_latency_ms'] = stats['total_latency_ms'] / stats['successful_dispatches']
        else:
            stats['avg_latency_ms'] = 0.0
        
        # 计算成功率
        if stats['total_dispatched'] > 0:
            stats['success_rate'] = stats['successful_dispatches'] / stats['total_dispatched']
        else:
            stats['success_rate'] = 0.0
        
        # 添加批处理器统计
        stats['batch_processors'] = {
            service: processor.get_buffer_size()
            for service, processor in self._batch_processors.items()
        }
        
        return stats
    
    async def dispatch_immediate(self, message: BaseRequest, priority: MessagePriority = MessagePriority.NORMAL) -> bool:
        """
        立即分发消息 (不经过队列)
        
        Args:
            message: 待分发的消息
            priority: 消息优先级
            
        Returns:
            是否成功分发
        """
        try:
            # 路由消息
            instance = await self.router.route_message(message)
            if not instance:
                return False
            
            # 获取服务客户端
            client = self.service_discovery.get_service_client(instance.service_name)
            if not client:
                return False
            
            # 直接发送
            request_data = message.to_dict()
            await client.call(
                instance.service_name.title(),
                "HandleMessage", 
                request_data
            )
            
            return True
            
        except Exception as e:
            logger.error(f"立即分发失败: {e}")
            return False