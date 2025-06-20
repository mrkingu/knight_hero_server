"""
聊天服务主应用
Chat Service Main Application

作者: lx
日期: 2025-06-18
描述: 聊天服务的主应用，负责服务启动、频道订阅初始化、消息推送任务等
"""
import asyncio
import signal
import sys
from typing import Dict, Any, Optional
import logging
from datetime import datetime

# 导入common框架
from common.database import (
    get_redis_cache, get_mongo_client, 
    close_redis_cache, close_mongo_client
)

# 导入聊天服务模块
from .handlers.chat_handler import get_chat_handler
from .services.message_service import get_message_storage, close_message_storage
from .services.message_pusher import get_message_pusher, close_message_pusher
from .channels.channel_manager import get_channel_manager, close_channel_manager
from .filters.word_filter import initialize_word_filter
from .models import ChatType, ChatMessage


class ChatService:
    """聊天服务主类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化聊天服务
        
        Args:
            config: 服务配置
        """
        self.config = config or {}
        self._chat_handler = None
        self._message_storage = None
        self._message_pusher = None
        self._channel_manager = None
        self._word_filter = None
        
        # 后台任务
        self._background_tasks = []
        
        # 服务状态
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        # 设置日志
        logging.basicConfig(
            level=getattr(logging, self.config.get("log_level", "INFO")),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self._logger = logging.getLogger(f"chat_service")
        
        # 服务配置
        self.SERVICE_NAME = "chat"
        
        # 清理任务配置
        self.CLEANUP_INTERVAL = self.config.get("cleanup_interval", 3600)  # 1小时
        self.STATS_INTERVAL = self.config.get("stats_interval", 300)  # 5分钟
    
    async def start(self) -> None:
        """启动聊天服务"""
        try:
            self._logger.info("正在启动聊天服务...")
            
            # 1. 初始化数据库连接
            await self._init_database()
            
            # 2. 初始化服务组件
            await self._init_components()
            
            # 3. 启动后台任务
            await self._start_background_tasks()
            
            # 4. 设置信号处理
            self._setup_signal_handlers()
            
            self._running = True
            self._logger.info("聊天服务启动成功")
            
            # 等待关闭信号
            await self._shutdown_event.wait()
            
        except Exception as e:
            self._logger.error(f"启动聊天服务失败: {e}")
            await self.shutdown()
            raise
    
    async def shutdown(self) -> None:
        """关闭聊天服务"""
        if not self._running:
            return
        
        self._logger.info("正在关闭聊天服务...")
        self._running = False
        
        try:
            # 1. 停止后台任务
            await self._stop_background_tasks()
            
            # 2. 关闭服务组件
            await self._close_components()
            
            # 3. 关闭数据库连接
            await self._close_database()
            
            self._logger.info("聊天服务已关闭")
            
        except Exception as e:
            self._logger.error(f"关闭聊天服务时发生错误: {e}")
        finally:
            self._shutdown_event.set()
    
    async def handle_message(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理来自gateway的消息
        
        Args:
            request_data: 请求数据
            
        Returns:
            处理结果
        """
        try:
            action = request_data.get("action")
            data = request_data.get("data", {})
            
            if not self._chat_handler:
                return {
                    "success": False,
                    "error": "聊天服务未初始化",
                    "error_code": "SERVICE_NOT_READY"
                }
            
            # 根据action分发处理
            if action == "send_message":
                return await self._handle_send_message(data)
            elif action == "get_history":
                return await self._handle_get_history(data)
            elif action == "get_offline_messages":
                return await self._handle_get_offline_messages(data)
            elif action == "join_channel":
                return await self._handle_join_channel(data)
            elif action == "leave_channel":
                return await self._handle_leave_channel(data)
            elif action == "create_channel":
                return await self._handle_create_channel(data)
            elif action == "get_channel_list":
                return await self._handle_get_channel_list(data)
            elif action == "delete_message":
                return await self._handle_delete_message(data)
            else:
                return {
                    "success": False,
                    "error": f"未知的操作: {action}",
                    "error_code": "UNKNOWN_ACTION"
                }
                
        except Exception as e:
            self._logger.error(f"处理消息失败: {e}, action: {request_data.get('action')}")
            return {
                "success": False,
                "error": "服务器内部错误",
                "error_code": "INTERNAL_ERROR"
            }
    
    # ========== 私有方法 ==========
    
    async def _init_database(self) -> None:
        """初始化数据库连接"""
        try:
            await get_redis_cache()
            await get_mongo_client()
            self._logger.info("数据库连接初始化成功")
        except Exception as e:
            self._logger.error(f"数据库连接初始化失败: {e}")
            raise
    
    async def _init_components(self) -> None:
        """初始化服务组件"""
        try:
            # 初始化敏感词过滤器
            custom_words_file = self.config.get("custom_words_file")
            self._word_filter = await initialize_word_filter(custom_words_file)
            
            # 初始化消息存储服务
            self._message_storage = await get_message_storage()
            
            # 初始化频道管理器
            self._channel_manager = await get_channel_manager()
            
            # 初始化消息推送器
            self._message_pusher = await get_message_pusher()
            
            # 初始化聊天处理器
            self._chat_handler = await get_chat_handler()
            
            self._logger.info("服务组件初始化成功")
            
        except Exception as e:
            self._logger.error(f"服务组件初始化失败: {e}")
            raise
    
    async def _start_background_tasks(self) -> None:
        """启动后台任务"""
        try:
            # 清理任务
            cleanup_task = asyncio.create_task(self._cleanup_worker())
            self._background_tasks.append(cleanup_task)
            
            # 统计任务
            stats_task = asyncio.create_task(self._stats_worker())
            self._background_tasks.append(stats_task)
            
            # 健康检查任务
            health_task = asyncio.create_task(self._health_check_worker())
            self._background_tasks.append(health_task)
            
            self._logger.info("后台任务启动成功")
            
        except Exception as e:
            self._logger.error(f"启动后台任务失败: {e}")
            raise
    
    async def _stop_background_tasks(self) -> None:
        """停止后台任务"""
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        # 等待所有任务完成
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
        self._logger.info("后台任务已停止")
    
    async def _close_components(self) -> None:
        """关闭服务组件"""
        try:
            await close_message_pusher()
            await close_channel_manager()
            await close_message_storage()
            
            self._logger.info("服务组件已关闭")
            
        except Exception as e:
            self._logger.error(f"关闭服务组件失败: {e}")
    
    async def _close_database(self) -> None:
        """关闭数据库连接"""
        try:
            await close_redis_cache()
            await close_mongo_client()
            self._logger.info("数据库连接已关闭")
        except Exception as e:
            self._logger.error(f"关闭数据库连接失败: {e}")
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self._logger.info(f"收到信号 {signum}，开始关闭服务...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    # ========== 消息处理方法 ==========
    
    async def _handle_send_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理发送消息"""
        required_fields = ["sender_id", "sender_name", "chat_type", "content"]
        
        for field in required_fields:
            if field not in data:
                return {
                    "success": False,
                    "error": f"缺少必要参数: {field}",
                    "error_code": "MISSING_PARAMETER"
                }
        
        # 转换聊天类型
        try:
            chat_type = ChatType(data["chat_type"])
        except ValueError:
            return {
                "success": False,
                "error": "无效的聊天类型",
                "error_code": "INVALID_CHAT_TYPE"
            }
        
        return await self._chat_handler.send_message(
            sender_id=data["sender_id"],
            sender_name=data["sender_name"],
            chat_type=chat_type,
            content=data["content"],
            channel=data.get("channel"),
            receiver_id=data.get("receiver_id"),
            receiver_name=data.get("receiver_name"),
            extra_data=data.get("extra_data")
        )
    
    async def _handle_get_history(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取历史消息"""
        player_id = data.get("player_id")
        channel = data.get("channel")
        
        if not player_id or not channel:
            return {
                "success": False,
                "error": "缺少必要参数",
                "error_code": "MISSING_PARAMETER"
            }
        
        return await self._chat_handler.get_history_messages(
            player_id=player_id,
            channel=channel,
            count=data.get("count", 50),
            before_timestamp=data.get("before_timestamp")
        )
    
    async def _handle_get_offline_messages(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取离线消息"""
        player_id = data.get("player_id")
        
        if not player_id:
            return {
                "success": False,
                "error": "缺少玩家ID",
                "error_code": "MISSING_PLAYER_ID"
            }
        
        return await self._chat_handler.get_offline_messages(player_id)
    
    async def _handle_join_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理加入频道"""
        player_id = data.get("player_id")
        channel_name = data.get("channel_name")
        
        if not player_id or not channel_name:
            return {
                "success": False,
                "error": "缺少必要参数",
                "error_code": "MISSING_PARAMETER"
            }
        
        return await self._chat_handler.join_channel(player_id, channel_name)
    
    async def _handle_leave_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理离开频道"""
        player_id = data.get("player_id")
        channel_name = data.get("channel_name")
        
        if not player_id or not channel_name:
            return {
                "success": False,
                "error": "缺少必要参数",
                "error_code": "MISSING_PARAMETER"
            }
        
        return await self._chat_handler.leave_channel(player_id, channel_name)
    
    async def _handle_create_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理创建频道"""
        creator_id = data.get("creator_id")
        channel_name = data.get("channel_name")
        
        if not creator_id or not channel_name:
            return {
                "success": False,
                "error": "缺少必要参数",
                "error_code": "MISSING_PARAMETER"
            }
        
        return await self._chat_handler.create_channel(
            creator_id=creator_id,
            channel_name=channel_name,
            description=data.get("description"),
            max_members=data.get("max_members")
        )
    
    async def _handle_get_channel_list(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取频道列表"""
        player_id = data.get("player_id")
        
        if not player_id:
            return {
                "success": False,
                "error": "缺少玩家ID",
                "error_code": "MISSING_PLAYER_ID"
            }
        
        return await self._chat_handler.get_channel_list(player_id)
    
    async def _handle_delete_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理删除消息"""
        player_id = data.get("player_id")
        message_id = data.get("message_id")
        channel = data.get("channel")
        
        if not all([player_id, message_id, channel]):
            return {
                "success": False,
                "error": "缺少必要参数",
                "error_code": "MISSING_PARAMETER"
            }
        
        return await self._chat_handler.delete_message(player_id, message_id, channel)
    
    # ========== 后台任务 ==========
    
    async def _cleanup_worker(self) -> None:
        """清理工作协程"""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                
                if not self._running:
                    break
                
                # 清理过期消息
                if self._message_storage:
                    cleaned_count = await self._message_storage.clean_expired_messages()
                    if cleaned_count > 0:
                        self._logger.info(f"清理了 {cleaned_count} 条过期消息")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"清理工作协程异常: {e}")
                await asyncio.sleep(60)
    
    async def _stats_worker(self) -> None:
        """统计工作协程"""
        while self._running:
            try:
                await asyncio.sleep(self.STATS_INTERVAL)
                
                if not self._running:
                    break
                
                # 收集统计信息
                stats = {}
                
                if self._channel_manager:
                    chat_stats = await self._channel_manager.get_statistics()
                    stats["chat"] = chat_stats.to_dict()
                
                if self._message_pusher:
                    push_stats = self._message_pusher.get_statistics()
                    stats["pusher"] = push_stats
                
                # 记录统计信息
                self._logger.info(f"服务统计: {stats}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"统计工作协程异常: {e}")
                await asyncio.sleep(60)
    
    async def _health_check_worker(self) -> None:
        """健康检查工作协程"""
        while self._running:
            try:
                await asyncio.sleep(30)  # 30秒检查一次
                
                if not self._running:
                    break
                
                # 检查各组件健康状态
                health_status = {
                    "timestamp": datetime.now().isoformat(),
                    "service": "chat",
                    "status": "healthy"
                }
                
                # 这里可以添加更详细的健康检查逻辑
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"健康检查异常: {e}")
                await asyncio.sleep(60)


# 全局服务实例
_chat_service: Optional[ChatService] = None


async def get_chat_service(config: Optional[Dict[str, Any]] = None) -> ChatService:
    """获取聊天服务实例"""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(config)
    return _chat_service


async def main():
    """主函数"""
    # 读取配置
    config = {
        "log_level": "INFO",
        "cleanup_interval": 3600,
        "stats_interval": 300
    }
    
    # 创建并启动服务
    service = await get_chat_service(config)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        print("\n收到中断信号，正在关闭服务...")
    except Exception as e:
        print(f"服务异常: {e}")
    finally:
        await service.shutdown()


if __name__ == "__main__":
    # 运行服务
    asyncio.run(main())