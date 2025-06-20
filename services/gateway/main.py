"""
Gateway网关服务主模块
Gateway Main Module

作者: lx
日期: 2025-06-18
描述: FastAPI应用初始化、uvloop集成、WebSocket路由、优雅关闭
"""
import asyncio
import uvloop
import signal
import sys
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

from .connection_manager import get_connection_manager, close_connection_manager, ConnectionPoolConfig
from .session_manager import get_session_manager, close_session_manager, SessionManagerConfig
from .connection import ConnectionConfig


class GatewayApp:
    """
    Gateway网关应用类
    
    整合FastAPI、连接管理器、会话管理器，提供完整的WebSocket网关服务
    """
    
    def __init__(self):
        """初始化Gateway应用"""
        self.app: Optional[FastAPI] = None
        self.connection_manager = None
        self.session_manager = None
        self._shutdown_event = asyncio.Event()
        self._running = False
        
        # 消息路由系统组件
        self._message_router = None
        self._message_queue = None
        self._message_dispatcher = None
        self._unified_handler = None
    
    async def initialize(self) -> bool:
        """
        初始化应用
        
        Returns:
            是否成功初始化
        """
        try:
            # 设置uvloop事件循环
            if sys.platform != 'win32':  # uvloop不支持Windows
                asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            
            # 初始化连接管理器
            pool_config = ConnectionPoolConfig(
                POOL_SIZE=10000,
                MAX_CONCURRENT_CONNECTIONS=8000,
                PRE_ALLOCATE_SIZE=1000
            )
            self.connection_manager = await get_connection_manager(pool_config)
            
            # 初始化会话管理器
            session_config = SessionManagerConfig(
                LOCAL_CACHE_SIZE=5000,
                DEFAULT_SESSION_TTL=30 * 60  # 30分钟
            )
            self.session_manager = await get_session_manager(session_config)
            
            # 初始化消息路由系统
            await self._initialize_routing_system()
            
            # 创建FastAPI应用
            self.app = self._create_app()
            
            print("Gateway应用初始化成功")
            return True
            
        except Exception as e:
            print(f"Gateway应用初始化失败: {e}")
            return False
    
    async def _initialize_routing_system(self) -> None:
        """初始化消息路由系统"""
        try:
            from .router import MessageRouter
            from .message_queue import PriorityMessageQueue
            from .message_dispatcher import MessageDispatcher
            from .handlers import UnifiedMessageHandler
            
            # 创建路由系统组件
            self._message_router = MessageRouter()
            self._message_queue = PriorityMessageQueue(
                max_size=10000,
                enable_deduplication=True,
                enable_backpressure=True
            )
            self._message_dispatcher = MessageDispatcher(
                self._message_router,
                self._message_queue
            )
            self._unified_handler = UnifiedMessageHandler(self._message_dispatcher)
            
            # 启动消息分发器
            await self._message_dispatcher.start()
            
            print("消息路由系统初始化成功")
            
        except Exception as e:
            print(f"消息路由系统初始化失败: {e}")
            # 不抛出异常，允许系统降级到原有处理方式
            self._message_router = None
            self._message_queue = None
            self._message_dispatcher = None
            self._unified_handler = None
    
    async def shutdown(self) -> None:
        """关闭应用"""
        print("开始关闭Gateway应用...")
        
        # 设置关闭标志
        self._running = False
        self._shutdown_event.set()
        
        try:
            # 关闭消息路由系统
            if self._message_dispatcher:
                await self._message_dispatcher.stop()
                print("消息路由系统已关闭")
            
            # 关闭会话管理器
            if self.session_manager:
                await close_session_manager()
                print("会话管理器已关闭")
            
            # 关闭连接管理器
            if self.connection_manager:
                await close_connection_manager()
                print("连接管理器已关闭")
            
            print("Gateway应用关闭完成")
            
        except Exception as e:
            print(f"关闭Gateway应用时发生错误: {e}")
    
    def _create_app(self) -> FastAPI:
        """
        创建FastAPI应用
        
        Returns:
            FastAPI应用实例
        """
        # 生命周期管理
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动时初始化
            self._running = True
            yield
            # 关闭时清理
            await self.shutdown()
        
        # 创建FastAPI应用
        app = FastAPI(
            title="Knight Hero Gateway Service",
            description="高性能WebSocket网关服务",
            version="1.0.0",
            lifespan=lifespan
        )
        
        # 注册路由
        self._register_routes(app)
        
        # 添加路由系统状态端点
        @app.get("/routing/stats")
        async def get_routing_stats():
            """获取路由系统统计信息"""
            if not self._message_router or not self._message_dispatcher or not self._unified_handler:
                return JSONResponse({
                    "status": "disabled",
                    "message": "路由系统未启用"
                })
            
            try:
                stats = {
                    "router": self._message_router.get_route_stats(),
                    "queue": self._message_queue.get_stats(),
                    "dispatcher": self._message_dispatcher.get_dispatch_stats(),
                    "handlers": self._unified_handler.get_handler_stats()
                }
                return JSONResponse(stats)
            except Exception as e:
                return JSONResponse({
                    "error": f"获取统计信息失败: {e}"
                }, status_code=500)
        
        return app
    
    def _register_routes(self, app: FastAPI) -> None:
        """
        注册路由
        
        Args:
            app: FastAPI应用实例
        """
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """
            WebSocket连接端点
            
            Args:
                websocket: WebSocket连接对象
            """
            await self.handle_websocket_connection(websocket)
        
        @app.get("/health")
        async def health_check():
            """健康检查端点"""
            return JSONResponse({
                "status": "healthy",
                "service": "gateway",
                "timestamp": asyncio.get_event_loop().time()
            })
        
        @app.get("/stats")
        async def get_stats():
            """获取统计信息端点"""
            try:
                stats = await self.get_service_stats()
                return JSONResponse(stats)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/admin/shutdown")
        async def admin_shutdown():
            """管理员关闭服务端点"""
            asyncio.create_task(self.shutdown())
            return JSONResponse({"message": "服务正在关闭..."})
    
    async def handle_websocket_connection(self, websocket: WebSocket) -> None:
        """
        处理WebSocket连接
        
        Args:
            websocket: WebSocket连接对象
        """
        connection = None
        session = None
        
        try:
            # 1. 创建连接对象
            connection = await self.connection_manager.create_connection(websocket)
            if not connection:
                await websocket.close(code=1013, reason="服务暂时不可用")
                return
            
            print(f"新连接建立: {connection}")
            
            # 2. 创建会话对象
            session = await self.session_manager.create_session(connection)
            if not session:
                await connection.close(code=1011, reason="无法创建会话")
                return
            
            print(f"会话创建成功: {session}")
            
            # 3. 绑定会话到连接管理器
            await self.connection_manager.bind_session(session.id, connection)
            
            # 4. 启动消息处理循环
            await self._message_loop(connection, session)
            
        except WebSocketDisconnect:
            print(f"客户端断开连接: {connection}")
        except Exception as e:
            print(f"处理WebSocket连接时发生错误: {e}")
        finally:
            # 5. 清理资源
            await self._cleanup_connection(connection, session)
    
    async def _message_loop(self, connection, session) -> None:
        """
        消息处理循环
        
        Args:
            connection: 连接对象
            session: 会话对象
        """
        try:
            while connection.is_connected and not self._shutdown_event.is_set():
                # 接收消息
                message = await connection.receive_message(timeout=1.0)
                if message:
                    # 处理消息
                    await self._handle_message(connection, session, message)
                
                # 检查会话状态
                if session.is_expired:
                    await connection.close(code=1000, reason="会话已过期")
                    break
                    
        except Exception as e:
            print(f"消息处理循环错误: {e}")
    
    async def _handle_message(self, connection, session, message) -> None:
        """
        处理单个消息 - 现在使用新的路由系统
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 消息对象
        """
        try:
            # 使用新的统一消息处理器
            if hasattr(self, '_unified_handler'):
                await self._unified_handler.handle_message(connection, session, message)
            else:
                # 兼容原有处理逻辑 (如果路由系统未初始化)
                await self._handle_message_legacy(connection, session, message)
                
        except Exception as e:
            print(f"处理消息时发生错误: {e}")
            await connection.send_dict({
                "type": "error",
                "message": "消息处理失败",
                "error_code": "MESSAGE_PROCESSING_ERROR"
            })
    
    async def _handle_message_legacy(self, connection, session, message) -> None:
        """
        原有的消息处理逻辑 (兼容)
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 消息对象
        """
        # 更新会话活跃时间
        session.update_activity()
        
        # 根据消息类型处理
        if message.type == "ping":
            # 处理ping消息
            await connection.send_dict({
                "type": "pong",
                "timestamp": asyncio.get_event_loop().time()
            }, "pong")
            
        elif message.type == "auth":
            # 处理认证消息
            await self._handle_auth_message(connection, session, message)
            
        elif message.type == "heartbeat":
            # 处理心跳消息
            session.update_ping()
            await connection.send_dict({
                "type": "heartbeat_ack",
                "timestamp": asyncio.get_event_loop().time()
            })
            
        elif message.type == "chat":
            # 处理聊天消息 - 使用新的集成
            from .chat_integration import handle_chat_message_from_gateway
            await handle_chat_message_from_gateway(connection, session, message)
            
        else:
            # 其他消息类型
            await self._handle_generic_message(connection, session, message)
    
    async def _handle_auth_message(self, connection, session, message) -> None:
        """
        处理认证消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 认证消息
        """
        try:
            auth_data = message.data
            user_id = auth_data.get("user_id")
            token = auth_data.get("token")
            
            if not user_id or not token:
                await connection.send_dict({
                    "type": "auth_response",
                    "success": False,
                    "message": "缺少认证信息"
                })
                return
            
            # 这里应该验证token的有效性
            # 简化处理，直接认证成功
            success = await self.session_manager.authenticate_session(
                session.id, 
                user_id,
                device_id=auth_data.get("device_id"),
                platform=auth_data.get("platform"),
                version=auth_data.get("version")
            )
            
            if success:
                # 认证成功后获取离线消息
                from .chat_integration import get_offline_messages_for_player
                offline_result = await get_offline_messages_for_player(connection, session)
                
                await connection.send_dict({
                    "type": "auth_response",
                    "success": True,
                    "session_id": str(session.id),
                    "user_id": user_id,
                    "message": "认证成功",
                    "offline_messages": offline_result.get("data", {}) if offline_result.get("success") else None
                })
                print(f"用户 {user_id} 认证成功, 会话: {session.id}")
            else:
                await connection.send_dict({
                    "type": "auth_response",
                    "success": False,
                    "message": "认证失败"
                })
                
        except Exception as e:
            print(f"处理认证消息时发生错误: {e}")
            await connection.send_dict({
                "type": "auth_response",
                "success": False,
                "message": "认证处理失败"
            })
    
    async def _handle_chat_message(self, connection, session, message) -> None:
        """
        处理聊天消息（示例）
        
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
            
            chat_data = message.data
            content = chat_data.get("content", "")
            
            # 构造广播消息
            broadcast_message = {
                "type": "chat",
                "user_id": session.attributes.user_id,
                "content": content,
                "timestamp": asyncio.get_event_loop().time()
            }
            
            # 广播给所有连接（示例）
            await self.connection_manager.broadcast_message(broadcast_message)
            
        except Exception as e:
            print(f"处理聊天消息时发生错误: {e}")
    
    async def _handle_generic_message(self, connection, session, message) -> None:
        """
        处理通用消息
        
        Args:
            connection: 连接对象
            session: 会话对象
            message: 消息对象
        """
        # 简单回显消息
        await connection.send_dict({
            "type": "echo",
            "original_type": message.type,
            "data": message.data,
            "timestamp": asyncio.get_event_loop().time()
        })
    
    async def _cleanup_connection(self, connection, session) -> None:
        """
        清理连接资源
        
        Args:
            connection: 连接对象
            session: 会话对象
        """
        try:
            if session:
                # 解绑会话
                await self.connection_manager.unbind_session(session.id)
                # 移除会话
                await self.session_manager.remove_session(session.id)
                print(f"会话已清理: {session.id}")
            
            if connection:
                # 释放连接
                await self.connection_manager.release_connection(connection)
                print(f"连接已释放: {connection.id}")
                
        except Exception as e:
            print(f"清理连接资源时发生错误: {e}")
    
    async def get_service_stats(self) -> Dict[str, Any]:
        """
        获取服务统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "service": "gateway",
            "running": self._running,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        if self.connection_manager:
            stats["connection_pool"] = self.connection_manager.get_pool_stats()
        
        if self.session_manager:
            stats["session_manager"] = self.session_manager.get_stats()
        
        return stats


# 全局Gateway应用实例
gateway_app = GatewayApp()


async def startup():
    """启动Gateway服务"""
    success = await gateway_app.initialize()
    if not success:
        print("Gateway服务启动失败")
        sys.exit(1)
    
    # 注册信号处理
    def signal_handler(signum, frame):
        print(f"接收到信号 {signum}，开始优雅关闭...")
        asyncio.create_task(gateway_app.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Gateway服务启动成功")
    return gateway_app.app


def get_app() -> FastAPI:
    """
    获取FastAPI应用实例（用于ASGI服务器）
    
    Returns:
        FastAPI应用实例
    """
    return gateway_app.app


if __name__ == "__main__":
    import uvicorn
    
    async def main():
        """主函数"""
        app = await startup()
        
        # 运行服务器
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            loop="uvloop",
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(config)
        await server.serve()
    
    # 运行主函数
    asyncio.run(main())