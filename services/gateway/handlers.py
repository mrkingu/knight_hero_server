"""
消息处理器模块
Message Handlers Module

作者: lx
日期: 2025-06-18
描述: 实现系统消息处理、业务消息转发、错误处理、消息统计
"""
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum
import logging

from common.protocol.core.base_request import BaseRequest
from common.protocol.core.message_type import MessageType
from services.gateway.connection import Connection
from services.gateway.session import Session
from .message_dispatcher import MessageDispatcher
from .message_queue import MessagePriority


logger = logging.getLogger(__name__)


class MessageCategory(Enum):
    """消息分类枚举"""
    SYSTEM = "system"      # 系统消息 (心跳、认证等)
    BUSINESS = "business"  # 业务消息 (需要转发)
    GATEWAY = "gateway"    # 网关自处理消息


@dataclass 
class MessageStats:
    """消息统计信息"""
    total_received: int = 0
    system_messages: int = 0
    business_messages: int = 0
    gateway_messages: int = 0
    errors: int = 0
    auth_success: int = 0
    auth_failure: int = 0
    heartbeats: int = 0
    forwards: int = 0
    response_time_ms: float = 0.0


class SystemMessageHandler:
    """系统消息处理器"""
    
    def __init__(self):
        """初始化系统消息处理器"""
        self.stats = MessageStats()
    
    async def handle_heartbeat(self, connection: Connection, session: Session, message: Any) -> None:
        """
        处理心跳消息
        
        Args:
            connection: 连接对象
            session: 会话对象  
            message: 心跳消息
        """
        try:
            self.stats.heartbeats += 1
            
            # 更新会话ping时间
            session.update_ping()
            
            # 发送心跳响应
            await connection.send_dict({
                "type": "heartbeat_ack",
                "timestamp": time.time(),
                "server_time": int(time.time() * 1000)
            })
            
            logger.debug(f"处理心跳消息: 会话={session.id}")
            
        except Exception as e:
            logger.error(f"处理心跳消息失败: {e}")
            self.stats.errors += 1
    
    async def handle_ping(self, connection: Connection, session: Session, message: Any) -> None:
        """
        处理ping消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: ping消息
        """
        try:
            # 发送pong响应
            await connection.send_dict({
                "type": "pong", 
                "timestamp": time.time(),
                "original_timestamp": getattr(message, 'timestamp', 0)
            })
            
            logger.debug(f"处理ping消息: 会话={session.id}")
            
        except Exception as e:
            logger.error(f"处理ping消息失败: {e}")
            self.stats.errors += 1
    
    async def handle_auth(self, connection: Connection, session: Session, message: Any) -> None:
        """
        处理认证消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 认证消息
        """
        try:
            # 提取认证数据
            auth_data = getattr(message, 'data', {})
            if hasattr(message, 'to_dict'):
                auth_data = message.to_dict()
            
            user_id = auth_data.get("user_id")
            token = auth_data.get("token") 
            player_id = auth_data.get("player_id")
            device_id = auth_data.get("device_id")
            
            if not user_id or not token:
                # 认证失败 - 缺少必要字段
                await self._send_auth_response(connection, False, "缺少必要的认证字段")
                self.stats.auth_failure += 1
                return
            
            # 执行认证逻辑 (这里简化处理)
            auth_success = await self._validate_auth(user_id, token)
            
            if auth_success:
                # 认证成功 - 更新会话
                success = await session.authenticate(
                    user_id=user_id,
                    player_id=player_id, 
                    device_id=device_id
                )
                
                if success:
                    await self._send_auth_response(connection, True, "认证成功")
                    self.stats.auth_success += 1
                    logger.info(f"用户认证成功: user_id={user_id}, session={session.id}")
                else:
                    await self._send_auth_response(connection, False, "会话认证失败")
                    self.stats.auth_failure += 1
            else:
                await self._send_auth_response(connection, False, "认证凭据无效")
                self.stats.auth_failure += 1
                
        except Exception as e:
            logger.error(f"处理认证消息失败: {e}")
            await self._send_auth_response(connection, False, "认证处理异常")
            self.stats.errors += 1
            self.stats.auth_failure += 1
    
    async def _validate_auth(self, user_id: str, token: str) -> bool:
        """
        验证认证凭据
        
        Args:
            user_id: 用户ID
            token: 认证令牌
            
        Returns:
            认证是否成功
        """
        # 这里应该对接实际的认证系统
        # 暂时使用简单的验证逻辑
        return len(user_id) > 0 and len(token) >= 8
    
    async def _send_auth_response(self, connection: Connection, success: bool, message: str) -> None:
        """
        发送认证响应
        
        Args:
            connection: 连接对象
            success: 认证是否成功
            message: 响应消息
        """
        response = {
            "type": "auth_response",
            "success": success,
            "message": message,
            "timestamp": time.time()
        }
        
        if not success:
            response["error_code"] = "AUTH_FAILED"
        
        await connection.send_dict(response)


class BusinessMessageHandler:
    """业务消息处理器"""
    
    def __init__(self, dispatcher: MessageDispatcher):
        """
        初始化业务消息处理器
        
        Args:
            dispatcher: 消息分发器
        """
        self.dispatcher = dispatcher
        self.stats = MessageStats()
    
    async def handle_business_message(self, connection: Connection, session: Session, message: BaseRequest) -> None:
        """
        处理业务消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 业务消息
        """
        try:
            start_time = time.time()
            
            # 检查会话认证状态
            if not session.is_authenticated:
                await self._send_error_response(
                    connection, 
                    "NOT_AUTHENTICATED", 
                    "请先进行身份认证"
                )
                return
            
            # 设置消息的玩家ID (如果未设置)
            if not getattr(message, 'player_id', None):
                if hasattr(message, 'player_id'):
                    message.player_id = session.attributes.player_id
            
            # 确定消息优先级
            priority = self._determine_priority(message)
            
            # 加入分发队列
            success = await self.dispatcher.queue.enqueue(message, priority)
            
            if success:
                self.stats.forwards += 1
                self.stats.business_messages += 1
                
                # 发送确认响应 (可选)
                await self._send_forward_ack(connection, message)
                
                logger.debug(f"业务消息已转发: msg_id={getattr(message, 'msg_id', 0)}, player_id={message.player_id}")
            else:
                await self._send_error_response(
                    connection,
                    "QUEUE_FULL", 
                    "消息队列已满，请稍后重试"
                )
            
            # 更新响应时间统计
            response_time = (time.time() - start_time) * 1000
            self.stats.response_time_ms = (self.stats.response_time_ms + response_time) / 2
            
        except Exception as e:
            logger.error(f"处理业务消息失败: {e}")
            await self._send_error_response(connection, "PROCESSING_ERROR", "消息处理失败")
            self.stats.errors += 1
    
    def _determine_priority(self, message: BaseRequest) -> MessagePriority:
        """
        确定消息优先级
        
        Args:
            message: 消息对象
            
        Returns:
            消息优先级
        """
        msg_id = getattr(message, 'msg_id', 0) or getattr(message, 'MESSAGE_TYPE', 0)
        
        # 根据消息ID范围确定优先级
        if 4000 <= msg_id <= 4999:  # 战斗消息
            return MessagePriority.HIGH
        elif 1000 <= msg_id <= 1999:  # 逻辑消息
            return MessagePriority.NORMAL
        elif 2000 <= msg_id <= 2999:  # 聊天消息
            return MessagePriority.NORMAL
        elif 3000 <= msg_id <= 3999:  # 其他战斗相关
            return MessagePriority.HIGH
        else:
            return MessagePriority.NORMAL
    
    async def _send_forward_ack(self, connection: Connection, message: BaseRequest) -> None:
        """
        发送转发确认响应
        
        Args:
            connection: 连接对象
            message: 原始消息
        """
        response = {
            "type": "forward_ack",
            "original_msg_id": getattr(message, 'msg_id', 0),
            "sequence": getattr(message, 'sequence', ''),
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _send_error_response(self, connection: Connection, error_code: str, error_message: str) -> None:
        """
        发送错误响应
        
        Args:
            connection: 连接对象
            error_code: 错误代码
            error_message: 错误消息
        """
        response = {
            "type": "error",
            "error_code": error_code,
            "message": error_message,
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)


class GatewayMessageHandler:
    """网关自处理消息处理器"""
    
    def __init__(self):
        """初始化网关消息处理器"""
        self.stats = MessageStats()
        
        # 支持的网关消息处理器
        self._handlers: Dict[int, Callable] = {
            9001: self._handle_gateway_status,
            9002: self._handle_gateway_stats,
            9003: self._handle_connection_info,
            9004: self._handle_session_info,
        }
    
    async def handle_gateway_message(self, connection: Connection, session: Session, message: Any) -> None:
        """
        处理网关自处理消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 网关消息
        """
        try:
            msg_id = getattr(message, 'msg_id', 0) or getattr(message, 'MESSAGE_TYPE', 0)
            
            handler = self._handlers.get(msg_id)
            if handler:
                await handler(connection, session, message)
                self.stats.gateway_messages += 1
            else:
                await self._handle_unknown_gateway_message(connection, session, message)
            
        except Exception as e:
            logger.error(f"处理网关消息失败: {e}")
            self.stats.errors += 1
    
    async def _handle_gateway_status(self, connection: Connection, session: Session, message: Any) -> None:
        """处理网关状态查询"""
        response = {
            "type": "gateway_status_response",
            "status": "running",
            "uptime": time.time(),
            "version": "1.0.0",
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _handle_gateway_stats(self, connection: Connection, session: Session, message: Any) -> None:
        """处理网关统计信息查询"""
        # 这里可以集成实际的统计信息
        response = {
            "type": "gateway_stats_response",
            "stats": {
                "system_messages": self.stats.system_messages,
                "business_messages": self.stats.business_messages,
                "gateway_messages": self.stats.gateway_messages,
                "errors": self.stats.errors
            },
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _handle_connection_info(self, connection: Connection, session: Session, message: Any) -> None:
        """处理连接信息查询"""
        connection_stats = connection.get_stats()
        
        response = {
            "type": "connection_info_response",
            "connection": connection_stats,
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _handle_session_info(self, connection: Connection, session: Session, message: Any) -> None:
        """处理会话信息查询"""
        session_data = session.to_dict()
        
        response = {
            "type": "session_info_response", 
            "session": session_data,
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _handle_unknown_gateway_message(self, connection: Connection, session: Session, message: Any) -> None:
        """处理未知网关消息"""
        response = {
            "type": "error",
            "error_code": "UNKNOWN_GATEWAY_MESSAGE",
            "message": f"未知的网关消息类型: {getattr(message, 'msg_id', 0)}",
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)


class UnifiedMessageHandler:
    """统一消息处理器"""
    
    def __init__(self, dispatcher: MessageDispatcher):
        """
        初始化统一消息处理器
        
        Args:
            dispatcher: 消息分发器
        """
        # 子处理器
        self.system_handler = SystemMessageHandler()
        self.business_handler = BusinessMessageHandler(dispatcher)
        self.gateway_handler = GatewayMessageHandler()
        
        # 总体统计
        self.total_stats = MessageStats()
        
        # 消息分类规则
        self._system_message_types = {
            "ping", "heartbeat", "auth", "logout"
        }
        
        self._system_message_ids = {
            MessageType.HEARTBEAT_REQUEST,
            MessageType.LOGIN_REQUEST,
            MessageType.LOGOUT_REQUEST,
        }
    
    async def handle_message(self, connection: Connection, session: Session, message: Any) -> None:
        """
        统一消息处理入口
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 消息对象
        """
        start_time = time.time()
        
        try:
            self.total_stats.total_received += 1
            
            # 更新会话活跃时间
            session.update_activity()
            
            # 确定消息分类
            category = self._categorize_message(message)
            
            # 根据分类调用对应处理器
            if category == MessageCategory.SYSTEM:
                await self._handle_system_message(connection, session, message)
                self.total_stats.system_messages += 1
                
            elif category == MessageCategory.BUSINESS:
                await self._handle_business_message(connection, session, message)
                self.total_stats.business_messages += 1
                
            elif category == MessageCategory.GATEWAY:
                await self._handle_gateway_message(connection, session, message)
                self.total_stats.gateway_messages += 1
                
            else:
                await self._handle_unknown_message(connection, session, message)
            
            # 更新响应时间
            response_time = (time.time() - start_time) * 1000
            self.total_stats.response_time_ms = (self.total_stats.response_time_ms + response_time) / 2
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            self.total_stats.errors += 1
            
            # 发送通用错误响应
            await self._send_generic_error(connection, str(e))
    
    def _categorize_message(self, message: Any) -> MessageCategory:
        """
        消息分类
        
        Args:
            message: 消息对象
            
        Returns:
            消息分类
        """
        # 检查消息类型字段
        message_type = getattr(message, 'type', '')
        if message_type in self._system_message_types:
            return MessageCategory.SYSTEM
        
        # 检查消息ID
        msg_id = getattr(message, 'msg_id', 0) or getattr(message, 'MESSAGE_TYPE', 0)
        
        if msg_id in self._system_message_ids:
            return MessageCategory.SYSTEM
        elif 9000 <= msg_id <= 9999:
            return MessageCategory.GATEWAY
        elif 1000 <= msg_id <= 8999:
            return MessageCategory.BUSINESS
        
        # 默认按消息类型处理
        if message_type:
            return MessageCategory.SYSTEM
        
        return MessageCategory.BUSINESS
    
    async def _handle_system_message(self, connection: Connection, session: Session, message: Any) -> None:
        """处理系统消息"""
        message_type = getattr(message, 'type', '')
        msg_id = getattr(message, 'msg_id', 0) or getattr(message, 'MESSAGE_TYPE', 0)
        
        if message_type == "heartbeat" or msg_id == MessageType.HEARTBEAT_REQUEST:
            await self.system_handler.handle_heartbeat(connection, session, message)
        elif message_type == "ping":
            await self.system_handler.handle_ping(connection, session, message)
        elif message_type == "auth" or msg_id == MessageType.LOGIN_REQUEST:
            await self.system_handler.handle_auth(connection, session, message)
        else:
            logger.warning(f"未知系统消息: type={message_type}, msg_id={msg_id}")
    
    async def _handle_business_message(self, connection: Connection, session: Session, message: Any) -> None:
        """处理业务消息"""
        # 将消息转换为BaseRequest格式
        if not isinstance(message, BaseRequest):
            # 如果不是BaseRequest，尝试转换
            if hasattr(message, 'to_dict'):
                message_dict = message.to_dict()
            else:
                # 简单消息对象转换
                message_dict = {
                    'msg_id': getattr(message, 'msg_id', 0),
                    'type': getattr(message, 'type', ''),
                    'data': getattr(message, 'data', {}),
                    'player_id': session.attributes.player_id
                }
            
            # 创建BaseRequest实例
            base_request = BaseRequest(player_id=session.attributes.player_id)
            base_request.from_dict(message_dict)
            message = base_request
        
        await self.business_handler.handle_business_message(connection, session, message)
    
    async def _handle_gateway_message(self, connection: Connection, session: Session, message: Any) -> None:
        """处理网关消息"""
        await self.gateway_handler.handle_gateway_message(connection, session, message)
    
    async def _handle_unknown_message(self, connection: Connection, session: Session, message: Any) -> None:
        """处理未知消息"""
        logger.warning(f"未知消息类型: {type(message)}, 内容: {message}")
        
        # 发送简单回显（兼容旧版本）
        response = {
            "type": "echo",
            "original_type": getattr(message, 'type', 'unknown'),
            "data": getattr(message, 'data', {}),
            "timestamp": time.time()
        }
        
        await connection.send_dict(response)
    
    async def _send_generic_error(self, connection: Connection, error: str) -> None:
        """发送通用错误响应"""
        response = {
            "type": "error",
            "error_code": "MESSAGE_PROCESSING_ERROR",
            "message": f"消息处理失败: {error}",
            "timestamp": time.time()
        }
        
        try:
            await connection.send_dict(response)
        except Exception as e:
            logger.error(f"发送错误响应失败: {e}")
    
    def get_handler_stats(self) -> Dict[str, Any]:
        """获取处理器统计信息"""
        return {
            "total": {
                "total_received": self.total_stats.total_received,
                "system_messages": self.total_stats.system_messages,
                "business_messages": self.total_stats.business_messages,
                "gateway_messages": self.total_stats.gateway_messages,
                "errors": self.total_stats.errors,
                "avg_response_time_ms": self.total_stats.response_time_ms
            },
            "system": {
                "heartbeats": self.system_handler.stats.heartbeats,
                "auth_success": self.system_handler.stats.auth_success,
                "auth_failure": self.system_handler.stats.auth_failure,
                "errors": self.system_handler.stats.errors
            },
            "business": {
                "forwards": self.business_handler.stats.forwards,
                "avg_response_time_ms": self.business_handler.stats.response_time_ms,
                "errors": self.business_handler.stats.errors
            },
            "gateway": {
                "gateway_messages": self.gateway_handler.stats.gateway_messages,
                "errors": self.gateway_handler.stats.errors
            }
        }