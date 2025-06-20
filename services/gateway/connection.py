"""
WebSocket连接封装模块
WebSocket Connection Module

作者: lx
日期: 2025-06-18
描述: 负责WebSocket连接的封装，包括读写队列、心跳检测、连接状态管理等
"""
import time
import asyncio
import json
from typing import Optional, Any, Dict, Union, TYPE_CHECKING
from enum import Enum
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from .session import Session


class ConnectionState(Enum):
    """连接状态枚举"""
    IDLE = "idle"              # 空闲状态
    CONNECTING = "connecting"  # 连接中
    CONNECTED = "connected"    # 已连接
    DISCONNECTING = "disconnecting"  # 断开中
    DISCONNECTED = "disconnected"    # 已断开
    ERROR = "error"           # 错误状态


@dataclass
class ConnectionConfig:
    """连接配置"""
    # 读写队列大小
    READ_QUEUE_SIZE: int = 1000
    WRITE_QUEUE_SIZE: int = 1000
    
    # 批处理配置
    BATCH_SIZE: int = 100
    BATCH_TIMEOUT: float = 0.01  # 10ms
    
    # 心跳配置
    HEARTBEAT_INTERVAL: int = 30  # 30秒
    HEARTBEAT_TIMEOUT: int = 60   # 60秒超时
    
    # WebSocket配置
    MAX_MESSAGE_SIZE: int = 65536  # 64KB
    COMPRESSION: Optional[str] = None  # 不压缩


@dataclass
class Message:
    """消息对象"""
    type: str                    # 消息类型
    data: Any                   # 消息数据
    timestamp: float            # 时间戳
    id: Optional[str] = None    # 消息ID
    reply_to: Optional[str] = None  # 回复消息ID


class Connection:
    """
    WebSocket连接封装类
    
    提供高性能的WebSocket连接管理，包括读写队列分离、心跳检测、连接状态管理等
    """
    
    def __init__(self, websocket: WebSocket, config: Optional[ConnectionConfig] = None):
        """
        初始化连接对象
        
        Args:
            websocket: FastAPI WebSocket对象
            config: 连接配置，默认使用标准配置
        """
        self.websocket = websocket
        self.config = config or ConnectionConfig()
        
        # 连接基础信息
        self.id = id(websocket)  # 使用WebSocket对象地址作为连接ID
        self.state = ConnectionState.IDLE
        self.created_at = time.time()
        self.connected_at: Optional[float] = None
        self.disconnected_at: Optional[float] = None
        
        # 客户端信息
        self.client_host = getattr(websocket.client, 'host', 'unknown') if websocket.client else 'unknown'
        self.client_port = getattr(websocket.client, 'port', 0) if websocket.client else 0
        
        # 队列
        self.read_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=self.config.READ_QUEUE_SIZE)
        self.write_queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=self.config.WRITE_QUEUE_SIZE)
        
        # 心跳相关
        self.last_ping = 0.0
        self.last_pong = 0.0
        self.ping_count = 0
        self.pong_count = 0
        
        # 统计信息
        self.bytes_sent = 0
        self.bytes_received = 0
        self.messages_sent = 0
        self.messages_received = 0
        self.errors_count = 0
        
        # 关联的会话
        self.session: Optional['Session'] = None
        
        # 任务管理
        self._read_task: Optional[asyncio.Task] = None
        self._write_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # 锁
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        
        # 状态标志
        self._closing = False
        self._closed = False
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.state == ConnectionState.CONNECTED and not self._closed
    
    @property
    def is_alive(self) -> bool:
        """检查连接是否存活"""
        if not self.is_connected:
            return False
        
        # 检查心跳超时
        if self.config.HEARTBEAT_TIMEOUT > 0:
            now = time.time()
            if self.last_ping > 0 and (now - self.last_ping) > self.config.HEARTBEAT_TIMEOUT:
                return False
        
        return True
    
    @property
    def duration(self) -> float:
        """获取连接持续时间"""
        if self.connected_at is None:
            return 0.0
        end_time = self.disconnected_at if self.disconnected_at else time.time()
        return end_time - self.connected_at
    
    async def accept(self) -> bool:
        """
        接受WebSocket连接
        
        Returns:
            是否成功接受连接
        """
        try:
            async with self._lock:
                if self.state != ConnectionState.IDLE:
                    return False
                
                self.state = ConnectionState.CONNECTING
                await self.websocket.accept()
                
                self.state = ConnectionState.CONNECTED
                self.connected_at = time.time()
                
                # 启动读写任务
                await self._start_tasks()
                
                return True
                
        except Exception as e:
            self.state = ConnectionState.ERROR
            self.errors_count += 1
            return False
    
    async def close(self, code: int = 1000, reason: str = "Normal closure") -> None:
        """
        关闭WebSocket连接
        
        Args:
            code: 关闭代码
            reason: 关闭原因
        """
        async with self._lock:
            if self._closing or self._closed:
                return
            
            self._closing = True
            self.state = ConnectionState.DISCONNECTING
            
            try:
                # 停止所有任务
                await self._stop_tasks()
                
                # 关闭WebSocket连接
                if self.websocket and not self._closed:
                    await self.websocket.close(code=code, reason=reason)
                
                self.state = ConnectionState.DISCONNECTED
                self.disconnected_at = time.time()
                
            except Exception as e:
                self.state = ConnectionState.ERROR
                self.errors_count += 1
            finally:
                self._closed = True
    
    async def send_message(self, message: Message) -> bool:
        """
        发送消息到写队列
        
        Args:
            message: 要发送的消息
            
        Returns:
            是否成功添加到队列
        """
        if not self.is_connected:
            return False
        
        try:
            # 非阻塞添加到写队列
            self.write_queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            # 队列满，记录错误
            self.errors_count += 1
            return False
    
    async def send_dict(self, data: Dict[str, Any], message_type: str = "data") -> bool:
        """
        发送字典格式消息
        
        Args:
            data: 消息数据
            message_type: 消息类型
            
        Returns:
            是否成功发送
        """
        message = Message(
            type=message_type,
            data=data,
            timestamp=time.time()
        )
        return await self.send_message(message)
    
    async def send_text(self, text: str, message_type: str = "text") -> bool:
        """
        发送文本消息
        
        Args:
            text: 文本内容
            message_type: 消息类型
            
        Returns:
            是否成功发送
        """
        message = Message(
            type=message_type,
            data=text,
            timestamp=time.time()
        )
        return await self.send_message(message)
    
    async def send_ping(self) -> bool:
        """
        发送ping消息
        
        Returns:
            是否成功发送
        """
        message = Message(
            type="ping",
            data={"timestamp": time.time()},
            timestamp=time.time()
        )
        success = await self.send_message(message)
        if success:
            self.last_ping = time.time()
            self.ping_count += 1
        return success
    
    async def receive_message(self, timeout: Optional[float] = None) -> Optional[Message]:
        """
        从读队列接收消息
        
        Args:
            timeout: 超时时间
            
        Returns:
            接收到的消息，超时返回None
        """
        try:
            message = await asyncio.wait_for(
                self.read_queue.get(),
                timeout=timeout
            )
            return message
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None
    
    async def read_loop(self) -> None:
        """读取循环 - 从WebSocket读取消息并放入读队列"""
        try:
            while self.is_connected and not self._closing:
                try:
                    # 接收WebSocket消息
                    raw_data = await self.websocket.receive()
                    
                    if 'text' in raw_data:
                        # 文本消息
                        text_data = raw_data['text']
                        self.bytes_received += len(text_data.encode('utf-8'))
                        
                        # 尝试解析JSON
                        try:
                            json_data = json.loads(text_data)
                            message = Message(
                                type=json_data.get('type', 'data'),
                                data=json_data.get('data', json_data),
                                timestamp=time.time(),
                                id=json_data.get('id'),
                                reply_to=json_data.get('reply_to')
                            )
                        except json.JSONDecodeError:
                            # 纯文本消息
                            message = Message(
                                type="text",
                                data=text_data,
                                timestamp=time.time()
                            )
                    
                    elif 'bytes' in raw_data:
                        # 二进制消息
                        bytes_data = raw_data['bytes']
                        self.bytes_received += len(bytes_data)
                        message = Message(
                            type="bytes",
                            data=bytes_data,
                            timestamp=time.time()
                        )
                    
                    else:
                        # 其他类型消息（连接关闭等）
                        break
                    
                    # 处理特殊消息类型
                    if message.type == "pong":
                        self.last_pong = time.time()
                        self.pong_count += 1
                        if self.session:
                            self.session.update_pong()
                        continue
                    
                    # 添加到读队列
                    try:
                        self.read_queue.put_nowait(message)
                        self.messages_received += 1
                        
                        # 更新会话活跃时间
                        if self.session:
                            self.session.update_activity()
                            
                    except asyncio.QueueFull:
                        # 读队列满，丢弃消息
                        self.errors_count += 1
                
                except WebSocketDisconnect:
                    # 客户端断开连接
                    break
                except Exception as e:
                    # 其他错误
                    self.errors_count += 1
                    await asyncio.sleep(0.1)  # 避免错误循环
                    
        except Exception as e:
            self.errors_count += 1
        finally:
            # 标记连接关闭
            if not self._closing:
                await self.close()
    
    async def write_loop(self) -> None:
        """写入循环 - 从写队列取消息并发送到WebSocket"""
        try:
            batch = []
            last_send = time.time()
            
            while self.is_connected and not self._closing:
                try:
                    # 尝试从写队列获取消息
                    try:
                        message = await asyncio.wait_for(
                            self.write_queue.get(),
                            timeout=self.config.BATCH_TIMEOUT
                        )
                        batch.append(message)
                    except asyncio.TimeoutError:
                        message = None
                    
                    # 检查是否需要发送批次
                    now = time.time()
                    should_send = (
                        len(batch) >= self.config.BATCH_SIZE or
                        (batch and (now - last_send) >= self.config.BATCH_TIMEOUT)
                    )
                    
                    if should_send and batch:
                        await self._send_batch(batch)
                        batch.clear()
                        last_send = now
                
                except Exception as e:
                    self.errors_count += 1
                    await asyncio.sleep(0.1)
            
            # 发送剩余消息
            if batch:
                await self._send_batch(batch)
                
        except Exception as e:
            self.errors_count += 1
    
    async def heartbeat_loop(self) -> None:
        """心跳循环 - 定期发送ping消息检测连接状态"""
        try:
            while self.is_connected and not self._closing:
                await asyncio.sleep(self.config.HEARTBEAT_INTERVAL)
                
                if self.is_connected and not self._closing:
                    # 发送ping
                    await self.send_ping()
                    
                    # 检查是否超时
                    if not self.is_alive:
                        await self.close(code=1001, reason="Heartbeat timeout")
                        break
                        
        except Exception as e:
            self.errors_count += 1
    
    async def _send_batch(self, batch: list[Message]) -> None:
        """
        批量发送消息
        
        Args:
            batch: 消息批次
        """
        async with self._write_lock:
            for message in batch:
                try:
                    await self._send_single_message(message)
                except Exception as e:
                    self.errors_count += 1
    
    async def _send_single_message(self, message: Message) -> None:
        """
        发送单个消息
        
        Args:
            message: 要发送的消息
        """
        try:
            # 构造发送数据
            if message.type in ("text", "json", "data"):
                # JSON格式
                send_data = {
                    "type": message.type,
                    "data": message.data,
                    "timestamp": message.timestamp
                }
                if message.id:
                    send_data["id"] = message.id
                if message.reply_to:
                    send_data["reply_to"] = message.reply_to
                
                text_data = json.dumps(send_data, ensure_ascii=False)
                await self.websocket.send_text(text_data)
                self.bytes_sent += len(text_data.encode('utf-8'))
                
            elif message.type == "bytes":
                # 二进制数据
                await self.websocket.send_bytes(message.data)
                self.bytes_sent += len(message.data)
                
            elif message.type == "ping":
                # ping消息
                ping_data = json.dumps({
                    "type": "ping",
                    "data": message.data,
                    "timestamp": message.timestamp
                })
                await self.websocket.send_text(ping_data)
                self.bytes_sent += len(ping_data.encode('utf-8'))
            
            self.messages_sent += 1
            
        except Exception as e:
            self.errors_count += 1
            raise
    
    async def _start_tasks(self) -> None:
        """启动异步任务"""
        self._read_task = asyncio.create_task(self.read_loop())
        self._write_task = asyncio.create_task(self.write_loop())
        
        if self.config.HEARTBEAT_INTERVAL > 0:
            self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())
    
    async def _stop_tasks(self) -> None:
        """停止异步任务"""
        tasks = [
            task for task in [self._read_task, self._write_task, self._heartbeat_task]
            if task and not task.done()
        ]
        
        if tasks:
            # 取消所有任务
            for task in tasks:
                task.cancel()
            
            # 等待任务完成
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取连接统计信息
        
        Returns:
            统计信息字典
        """
        return {
            'id': self.id,
            'state': self.state.value,
            'client_host': self.client_host,
            'client_port': self.client_port,
            'created_at': self.created_at,
            'connected_at': self.connected_at,
            'disconnected_at': self.disconnected_at,
            'duration': self.duration,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'errors_count': self.errors_count,
            'ping_count': self.ping_count,
            'pong_count': self.pong_count,
            'last_ping': self.last_ping,
            'last_pong': self.last_pong,
            'read_queue_size': self.read_queue.qsize(),
            'write_queue_size': self.write_queue.qsize(),
            'is_alive': self.is_alive
        }
    
    def __str__(self) -> str:
        """字符串表示"""
        return (f"Connection(id={self.id}, state={self.state.value}, "
                f"client={self.client_host}:{self.client_port}, duration={self.duration:.2f}s)")
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()