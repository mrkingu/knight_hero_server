"""
聊天消息集成模块
Chat Message Integration Module

作者: lx
日期: 2025-06-18
描述: 将聊天服务集成到网关，处理聊天消息路由和推送
"""
import asyncio
import time
from typing import Dict, Any, Optional, List
import logging

from services.chat.main import get_chat_service


class ChatMessageIntegration:
    """聊天消息集成器"""
    
    def __init__(self):
        """初始化聊天消息集成器"""
        self._chat_service = None
        self._logger = logging.getLogger(__name__)
        
        # 聊天消息类型映射
        self.CHAT_MESSAGE_TYPES = {
            "send_message": 2001,      # 发送消息
            "get_history": 2002,       # 获取历史消息
            "join_channel": 2003,      # 加入频道
            "leave_channel": 2004,     # 离开频道
            "create_channel": 2005,    # 创建频道
            "get_channel_list": 2006,  # 获取频道列表
            "get_offline_messages": 2007,  # 获取离线消息
            "delete_message": 2008,    # 删除消息
        }
        
    async def initialize(self) -> bool:
        """
        初始化聊天集成
        
        Returns:
            初始化是否成功
        """
        try:
            # 获取聊天服务实例
            self._chat_service = await get_chat_service()
            
            self._logger.info("聊天消息集成初始化成功")
            return True
            
        except Exception as e:
            self._logger.error(f"聊天消息集成初始化失败: {e}")
            return False
    
    async def handle_chat_message(self, connection, session, message) -> None:
        """
        处理聊天消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 聊天消息
        """
        try:
            if not session.is_authenticated:
                await connection.send_dict({
                    "type": "error",
                    "message": "请先进行身份认证",
                    "error_code": "NOT_AUTHENTICATED"
                })
                return
            
            # 获取消息数据
            message_data = message.data if hasattr(message, 'data') else {}
            action = message_data.get("action", "send_message")
            
            # 构造聊天服务请求
            request_data = {
                "action": action,
                "data": self._prepare_chat_request(session, message_data)
            }
            
            # 调用聊天服务
            if self._chat_service:
                response = await self._chat_service.handle_message(request_data)
            else:
                response = {
                    "success": False,
                    "error": "聊天服务未就绪",
                    "error_code": "SERVICE_NOT_READY"
                }
            
            # 发送响应
            await connection.send_dict({
                "type": "chat_response",
                "action": action,
                "success": response.get("success", False),
                "data": response,
                "timestamp": time.time()
            })
            
            self._logger.debug(f"处理聊天消息: {action}, 玩家: {session.attributes.user_id}")
            
        except Exception as e:
            self._logger.error(f"处理聊天消息失败: {e}")
            await connection.send_dict({
                "type": "error",
                "message": "聊天消息处理失败",
                "error_code": "CHAT_PROCESSING_ERROR"
            })
    
    async def handle_send_message(self, connection, session, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理发送消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message_data: 消息数据
            
        Returns:
            处理结果
        """
        try:
            # 准备聊天请求数据
            chat_data = self._prepare_chat_request(session, message_data)
            
            request_data = {
                "action": "send_message",
                "data": chat_data
            }
            
            # 调用聊天服务
            if self._chat_service:
                response = await self._chat_service.handle_message(request_data)
                
                # 如果发送成功，可能需要广播给其他连接
                if response.get("success") and response.get("broadcast_count", 0) > 0:
                    await self._handle_message_broadcast(response, message_data)
                
                return response
            else:
                return {
                    "success": False,
                    "error": "聊天服务未就绪",
                    "error_code": "SERVICE_NOT_READY"
                }
                
        except Exception as e:
            self._logger.error(f"发送聊天消息失败: {e}")
            return {
                "success": False,
                "error": "发送消息失败",
                "error_code": "SEND_MESSAGE_ERROR"
            }
    
    async def handle_get_history(self, connection, session, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取历史消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message_data: 消息数据
            
        Returns:
            处理结果
        """
        try:
            chat_data = self._prepare_chat_request(session, message_data)
            
            request_data = {
                "action": "get_history",
                "data": chat_data
            }
            
            if self._chat_service:
                return await self._chat_service.handle_message(request_data)
            else:
                return {
                    "success": False,
                    "error": "聊天服务未就绪",
                    "error_code": "SERVICE_NOT_READY"
                }
                
        except Exception as e:
            self._logger.error(f"获取历史消息失败: {e}")
            return {
                "success": False,
                "error": "获取历史消息失败",
                "error_code": "GET_HISTORY_ERROR"
            }
    
    async def handle_join_channel(self, connection, session, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理加入频道
        
        Args:
            connection: 连接对象
            session: 会话对象
            message_data: 消息数据
            
        Returns:
            处理结果
        """
        try:
            chat_data = self._prepare_chat_request(session, message_data)
            
            request_data = {
                "action": "join_channel",
                "data": chat_data
            }
            
            if self._chat_service:
                return await self._chat_service.handle_message(request_data)
            else:
                return {
                    "success": False,
                    "error": "聊天服务未就绪",
                    "error_code": "SERVICE_NOT_READY"
                }
                
        except Exception as e:
            self._logger.error(f"加入频道失败: {e}")
            return {
                "success": False,
                "error": "加入频道失败",
                "error_code": "JOIN_CHANNEL_ERROR"
            }
    
    async def handle_get_offline_messages(self, connection, session) -> Dict[str, Any]:
        """
        处理获取离线消息（登录时调用）
        
        Args:
            connection: 连接对象
            session: 会话对象
            
        Returns:
            处理结果
        """
        try:
            if not session.is_authenticated:
                return {
                    "success": False,
                    "error": "未认证",
                    "error_code": "NOT_AUTHENTICATED"
                }
            
            request_data = {
                "action": "get_offline_messages",
                "data": {
                    "player_id": session.attributes.user_id
                }
            }
            
            if self._chat_service:
                return await self._chat_service.handle_message(request_data)
            else:
                return {
                    "success": False,
                    "error": "聊天服务未就绪",
                    "error_code": "SERVICE_NOT_READY"
                }
                
        except Exception as e:
            self._logger.error(f"获取离线消息失败: {e}")
            return {
                "success": False,
                "error": "获取离线消息失败",
                "error_code": "GET_OFFLINE_MESSAGES_ERROR"
            }
    
    def _prepare_chat_request(self, session, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备聊天请求数据
        
        Args:
            session: 会话对象
            message_data: 原始消息数据
            
        Returns:
            聊天请求数据
        """
        # 基础数据
        chat_data = {
            "player_id": session.attributes.user_id,
            "player_name": getattr(session.attributes, 'nickname', session.attributes.user_id),
        }
        
        # 合并消息数据
        chat_data.update(message_data)
        
        # 为发送消息添加发送者信息
        if message_data.get("action") == "send_message" or not message_data.get("action"):
            chat_data.update({
                "sender_id": session.attributes.user_id,
                "sender_name": getattr(session.attributes, 'nickname', session.attributes.user_id),
            })
        
        return chat_data
    
    async def _handle_message_broadcast(self, response: Dict[str, Any], original_data: Dict[str, Any]) -> None:
        """
        处理消息广播（如果需要推送给其他连接）
        
        Args:
            response: 聊天服务响应
            original_data: 原始消息数据
        """
        try:
            # 这里可以集成消息推送逻辑
            # 例如：通过Redis Pub/Sub通知其他gateway实例
            
            # 记录广播信息
            broadcast_count = response.get("broadcast_count", 0)
            if broadcast_count > 0:
                self._logger.debug(f"消息已广播给 {broadcast_count} 个接收者")
                
        except Exception as e:
            self._logger.warning(f"处理消息广播失败: {e}")
    
    def get_message_type_for_action(self, action: str) -> Optional[int]:
        """
        根据聊天动作获取消息类型ID
        
        Args:
            action: 聊天动作
            
        Returns:
            消息类型ID
        """
        return self.CHAT_MESSAGE_TYPES.get(action)


# 全局集成实例
_chat_integration: Optional[ChatMessageIntegration] = None


async def get_chat_integration() -> ChatMessageIntegration:
    """获取聊天消息集成器实例"""
    global _chat_integration
    if _chat_integration is None:
        _chat_integration = ChatMessageIntegration()
        await _chat_integration.initialize()
    return _chat_integration


# 便捷函数，供gateway使用
async def handle_chat_message_from_gateway(connection, session, message) -> None:
    """
    从网关处理聊天消息的便捷函数
    
    Args:
        connection: 连接对象
        session: 会话对象
        message: 消息对象
    """
    integration = await get_chat_integration()
    await integration.handle_chat_message(connection, session, message)


async def get_offline_messages_for_player(connection, session) -> Dict[str, Any]:
    """
    为玩家获取离线消息的便捷函数
    
    Args:
        connection: 连接对象
        session: 会话对象
        
    Returns:
        离线消息结果
    """
    integration = await get_chat_integration()
    return await integration.handle_get_offline_messages(connection, session)