"""
消息推送器
Message Pusher

作者: lx
日期: 2025-06-18
描述: 高性能的消息推送服务，支持批量推送和推送优化
"""
import asyncio
import time
from typing import Dict, List, Set, Optional, Any, Callable
from dataclasses import dataclass
import logging

from common.database import get_redis_cache


@dataclass
class PushMessage:
    """推送消息"""
    player_id: str
    message: Dict[str, Any]
    priority: int = 0  # 优先级，数字越大优先级越高
    timestamp: float = 0.0
    retry_count: int = 0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class MessagePusher:
    """消息推送器"""
    
    def __init__(self, 
                 push_callback: Optional[Callable] = None,
                 batch_size: int = 100,
                 batch_timeout: float = 0.1):
        """
        初始化消息推送器
        
        Args:
            push_callback: 推送回调函数
            batch_size: 批次大小
            batch_timeout: 批次超时时间（秒）
        """
        self._push_callback = push_callback
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        
        # 推送队列
        self._push_queue = asyncio.Queue(maxsize=10000)
        self._priority_queue = asyncio.PriorityQueue(maxsize=5000)
        
        # 工作协程
        self._push_workers: List[asyncio.Task] = []
        self._priority_worker: Optional[asyncio.Task] = None
        
        # 在线玩家管理
        self._online_players: Set[str] = set()
        self._player_connections: Dict[str, Any] = {}  # player_id -> connection
        
        # 统计信息
        self._stats = {
            "total_pushed": 0,
            "batch_pushed": 0,
            "failed_pushes": 0,
            "online_players": 0,
            "queue_size": 0
        }
        
        self._redis_client = None
        self._logger = logging.getLogger(__name__)
        
        # 配置
        self.WORKER_COUNT = 3  # 推送工作协程数量
        self.MAX_RETRY_COUNT = 3  # 最大重试次数
        self.RETRY_DELAY = 1.0  # 重试延迟（秒）
    
    async def initialize(self, push_callback: Optional[Callable] = None) -> bool:
        """
        初始化推送器
        
        Args:
            push_callback: 推送回调函数
            
        Returns:
            初始化是否成功
        """
        try:
            if push_callback:
                self._push_callback = push_callback
            
            # 获取Redis客户端
            self._redis_client = await get_redis_cache()
            
            # 启动工作协程
            await self._start_workers()
            
            self._logger.info("消息推送器初始化成功")
            return True
            
        except Exception as e:
            self._logger.error(f"消息推送器初始化失败: {e}")
            return False
    
    async def shutdown(self) -> None:
        """关闭推送器"""
        # 停止工作协程
        for worker in self._push_workers:
            if not worker.done():
                worker.cancel()
        
        if self._priority_worker and not self._priority_worker.done():
            self._priority_worker.cancel()
        
        # 等待所有任务完成
        all_tasks = self._push_workers + ([self._priority_worker] if self._priority_worker else [])
        
        for task in all_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("消息推送器已关闭")
    
    async def push_message(self, player_ids: List[str], message: Dict[str, Any]) -> None:
        """
        推送消息给玩家列表
        
        Args:
            player_ids: 玩家ID列表
            message: 消息内容
        """
        for player_id in player_ids:
            push_msg = PushMessage(player_id=player_id, message=message)
            
            try:
                self._push_queue.put_nowait(push_msg)
            except asyncio.QueueFull:
                self._logger.warning(f"推送队列已满，丢弃消息: {player_id}")
                self._stats["failed_pushes"] += 1
    
    async def push_priority_message(self, 
                                   player_ids: List[str], 
                                   message: Dict[str, Any],
                                   priority: int = 10) -> None:
        """
        推送高优先级消息
        
        Args:
            player_ids: 玩家ID列表
            message: 消息内容
            priority: 优先级（数字越大优先级越高）
        """
        for player_id in player_ids:
            push_msg = PushMessage(
                player_id=player_id, 
                message=message, 
                priority=priority
            )
            
            try:
                # 优先级队列使用负数来实现最大堆
                await self._priority_queue.put((-priority, time.time(), push_msg))
            except asyncio.QueueFull:
                self._logger.warning(f"优先级队列已满，丢弃消息: {player_id}")
                self._stats["failed_pushes"] += 1
    
    async def push_single_message(self, player_id: str, message: Dict[str, Any]) -> bool:
        """
        推送单条消息
        
        Args:
            player_id: 玩家ID
            message: 消息内容
            
        Returns:
            推送是否成功
        """
        if not self._is_player_online(player_id):
            return False
        
        try:
            if self._push_callback:
                return await self._push_callback(player_id, message)
            else:
                # 使用Redis发布订阅
                return await self._push_via_redis(player_id, message)
                
        except Exception as e:
            self._logger.error(f"推送单条消息失败: {e}, player: {player_id}")
            return False
    
    async def broadcast_message(self, message: Dict[str, Any]) -> int:
        """
        广播消息给所有在线玩家
        
        Args:
            message: 消息内容
            
        Returns:
            成功推送的玩家数量
        """
        online_players = list(self._online_players)
        await self.push_message(online_players, message)
        return len(online_players)
    
    def add_player_connection(self, player_id: str, connection: Any) -> None:
        """
        添加玩家连接
        
        Args:
            player_id: 玩家ID
            connection: 连接对象
        """
        self._online_players.add(player_id)
        self._player_connections[player_id] = connection
        self._stats["online_players"] = len(self._online_players)
        
        self._logger.debug(f"添加玩家连接: {player_id}")
    
    def remove_player_connection(self, player_id: str) -> None:
        """
        移除玩家连接
        
        Args:
            player_id: 玩家ID
        """
        self._online_players.discard(player_id)
        self._player_connections.pop(player_id, None)
        self._stats["online_players"] = len(self._online_players)
        
        self._logger.debug(f"移除玩家连接: {player_id}")
    
    def get_online_players(self) -> List[str]:
        """获取在线玩家列表"""
        return list(self._online_players)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取推送统计信息"""
        self._stats["queue_size"] = self._push_queue.qsize()
        self._stats["priority_queue_size"] = self._priority_queue.qsize()
        return self._stats.copy()
    
    def _is_player_online(self, player_id: str) -> bool:
        """检查玩家是否在线"""
        return player_id in self._online_players
    
    # ========== 私有方法 ==========
    
    async def _start_workers(self) -> None:
        """启动工作协程"""
        # 启动普通推送工作协程
        for i in range(self.WORKER_COUNT):
            worker = asyncio.create_task(self._push_worker(f"worker-{i}"))
            self._push_workers.append(worker)
        
        # 启动优先级推送工作协程
        self._priority_worker = asyncio.create_task(self._priority_push_worker())
    
    async def _push_worker(self, worker_name: str) -> None:
        """推送工作协程"""
        batch = []
        
        while True:
            try:
                # 收集批量消息
                deadline = time.time() + self._batch_timeout
                
                while len(batch) < self._batch_size and time.time() < deadline:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    
                    try:
                        push_msg = await asyncio.wait_for(
                            self._push_queue.get(),
                            timeout=remaining
                        )
                        
                        # 只推送给在线玩家
                        if self._is_player_online(push_msg.player_id):
                            batch.append(push_msg)
                        
                    except asyncio.TimeoutError:
                        break
                
                # 批量推送
                if batch:
                    await self._batch_push(batch, worker_name)
                    batch = []
                    
            except asyncio.CancelledError:
                # 处理剩余消息
                if batch:
                    await self._batch_push(batch, worker_name)
                break
            except Exception as e:
                self._logger.error(f"推送工作协程异常: {e}, worker: {worker_name}")
                await asyncio.sleep(1)
    
    async def _priority_push_worker(self) -> None:
        """优先级推送工作协程"""
        while True:
            try:
                # 获取优先级消息
                _, _, push_msg = await self._priority_queue.get()
                
                # 立即推送优先级消息
                if self._is_player_online(push_msg.player_id):
                    success = await self._push_single(push_msg)
                    if success:
                        self._stats["total_pushed"] += 1
                    else:
                        await self._handle_push_failure(push_msg)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"优先级推送工作协程异常: {e}")
                await asyncio.sleep(1)
    
    async def _batch_push(self, batch: List[PushMessage], worker_name: str) -> None:
        """批量推送消息"""
        if not batch:
            return
        
        start_time = time.time()
        success_count = 0
        
        try:
            # 按玩家分组
            player_messages = {}
            for push_msg in batch:
                if push_msg.player_id not in player_messages:
                    player_messages[push_msg.player_id] = []
                player_messages[push_msg.player_id].append(push_msg)
            
            # 并发推送
            tasks = []
            for player_id, messages in player_messages.items():
                task = asyncio.create_task(
                    self._push_to_player(player_id, messages)
                )
                tasks.append(task)
            
            # 等待所有推送完成
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            for result in results:
                if isinstance(result, int):
                    success_count += result
                elif isinstance(result, Exception):
                    self._logger.warning(f"批量推送部分失败: {result}")
            
            # 更新统计
            self._stats["total_pushed"] += success_count
            self._stats["batch_pushed"] += 1
            
            elapsed = time.time() - start_time
            self._logger.debug(
                f"批量推送完成: {worker_name}, "
                f"消息数: {len(batch)}, 成功: {success_count}, "
                f"耗时: {elapsed:.3f}s"
            )
            
        except Exception as e:
            self._logger.error(f"批量推送失败: {e}, worker: {worker_name}")
            
            # 处理失败的消息
            for push_msg in batch:
                await self._handle_push_failure(push_msg)
    
    async def _push_to_player(self, player_id: str, messages: List[PushMessage]) -> int:
        """推送消息到指定玩家"""
        success_count = 0
        
        for push_msg in messages:
            try:
                success = await self._push_single(push_msg)
                if success:
                    success_count += 1
                else:
                    await self._handle_push_failure(push_msg)
                    
            except Exception as e:
                self._logger.warning(f"推送到玩家失败: {e}, player: {player_id}")
                await self._handle_push_failure(push_msg)
        
        return success_count
    
    async def _push_single(self, push_msg: PushMessage) -> bool:
        """推送单条消息"""
        try:
            if self._push_callback:
                return await self._push_callback(push_msg.player_id, push_msg.message)
            else:
                return await self._push_via_redis(push_msg.player_id, push_msg.message)
                
        except Exception as e:
            self._logger.warning(f"推送消息失败: {e}, player: {push_msg.player_id}")
            return False
    
    async def _push_via_redis(self, player_id: str, message: Dict[str, Any]) -> bool:
        """通过Redis推送消息"""
        if not self._redis_client:
            return False
        
        try:
            redis = self._redis_client.client
            channel = f"player:{player_id}:messages"
            
            # 发布消息
            import orjson
            message_data = orjson.dumps(message).decode('utf-8')
            await redis.publish(channel, message_data)
            
            return True
            
        except Exception as e:
            self._logger.error(f"Redis推送失败: {e}, player: {player_id}")
            return False
    
    async def _handle_push_failure(self, push_msg: PushMessage) -> None:
        """处理推送失败"""
        push_msg.retry_count += 1
        
        if push_msg.retry_count <= self.MAX_RETRY_COUNT:
            # 重试
            await asyncio.sleep(self.RETRY_DELAY)
            try:
                self._push_queue.put_nowait(push_msg)
            except asyncio.QueueFull:
                self._stats["failed_pushes"] += 1
        else:
            # 超过重试次数，记录失败
            self._stats["failed_pushes"] += 1
            self._logger.warning(
                f"消息推送最终失败: player: {push_msg.player_id}, "
                f"retry_count: {push_msg.retry_count}"
            )


# 全局实例
_message_pusher: Optional[MessagePusher] = None


async def get_message_pusher(push_callback: Optional[Callable] = None) -> MessagePusher:
    """获取消息推送器实例"""
    global _message_pusher
    if _message_pusher is None:
        _message_pusher = MessagePusher()
        await _message_pusher.initialize(push_callback)
    return _message_pusher


async def close_message_pusher() -> None:
    """关闭消息推送器"""
    global _message_pusher
    if _message_pusher:
        await _message_pusher.shutdown()
        _message_pusher = None