"""
Logic服务基类
Base Logic Service Class

作者: mrkingu
日期: 2025-06-20
描述: 所有业务服务的基类，提供通用的业务逻辑功能
"""

from abc import ABC
from typing import Any, Optional, Dict
import logging

from common.ioc import BaseService

logger = logging.getLogger(__name__)


class BaseLogicService(BaseService, ABC):
    """
    Logic服务基类
    
    所有业务服务都应该继承这个基类
    提供通用的业务验证和处理功能
    """
    
    def __init__(self):
        """初始化Logic服务"""
        super().__init__()
        self._player_cache: Dict[str, Dict[str, Any]] = {}
        self._config_cache: Dict[str, Any] = {}
    
    async def on_initialize(self) -> None:
        """服务初始化"""
        try:
            self.logger.info(f"Initializing logic service: {self._service_name}")
            
            # 预加载配置
            await self._load_service_config()
            
            # 初始化缓存
            self._player_cache.clear()
            
            self.logger.info(f"Logic service initialized successfully: {self._service_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize logic service {self._service_name}: {e}")
            raise
    
    async def _load_service_config(self) -> None:
        """
        加载服务配置
        
        子类可以重写此方法来加载特定的配置
        """
        # 这里可以从配置管理器加载配置
        # config_manager = self.get_service("ConfigManager")
        # self._config_cache = await config_manager.get_service_config(self._service_name)
        pass
    
    async def validate_player(self, player_id: str) -> bool:
        """
        通用的玩家验证
        
        Args:
            player_id: 玩家ID
            
        Returns:
            是否有效
        """
        try:
            if not player_id or len(player_id) < 3:
                return False
            
            # 可以添加更多验证逻辑：
            # - 检查玩家是否存在
            # - 检查玩家状态
            # - 检查是否被封禁等
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating player {player_id}: {e}")
            return False
    
    async def validate_player_action(
        self,
        player_id: str,
        action: str,
        **params
    ) -> Dict[str, Any]:
        """
        验证玩家行为
        
        Args:
            player_id: 玩家ID
            action: 行为类型
            **params: 行为参数
            
        Returns:
            验证结果 {"valid": bool, "reason": str}
        """
        try:
            # 基础玩家验证
            if not await self.validate_player(player_id):
                return {"valid": False, "reason": "Invalid player"}
            
            # 这里可以添加具体的行为验证逻辑
            # 子类可以重写此方法添加特定验证
            
            return {"valid": True, "reason": ""}
            
        except Exception as e:
            self.logger.error(f"Error validating player action {player_id} {action}: {e}")
            return {"valid": False, "reason": f"Validation error: {e}"}
    
    async def get_player_cache(self, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家缓存数据
        
        Args:
            player_id: 玩家ID
            
        Returns:
            缓存数据
        """
        return self._player_cache.get(player_id)
    
    async def set_player_cache(self, player_id: str, data: Dict[str, Any]) -> None:
        """
        设置玩家缓存数据
        
        Args:
            player_id: 玩家ID
            data: 缓存数据
        """
        self._player_cache[player_id] = data
    
    async def clear_player_cache(self, player_id: str) -> None:
        """
        清除玩家缓存
        
        Args:
            player_id: 玩家ID
        """
        if player_id in self._player_cache:
            del self._player_cache[player_id]
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self._config_cache.get(key, default)
    
    async def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发送事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        try:
            # 这里应该通过事件系统发送事件
            # event_manager = self.get_service("EventManager")
            # await event_manager.emit(event_type, data)
            
            self.logger.debug(f"Event emitted: {event_type} with data: {data}")
            
        except Exception as e:
            self.logger.error(f"Error emitting event {event_type}: {e}")
    
    async def log_business_action(
        self,
        player_id: str,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """
        记录业务行为日志
        
        Args:
            player_id: 玩家ID
            action: 行为类型
            params: 行为参数
            result: 行为结果
        """
        try:
            log_data = {
                "service": self._service_name,
                "player_id": player_id,
                "action": action,
                "params": params,
                "result": result,
                "timestamp": __import__('time').time()
            }
            
            # 这里应该通过日志系统记录
            # log_service = self.get_service("LogService")
            # await log_service.log_business_action(log_data)
            
            self.logger.info(f"Business action logged: {action} for {player_id}")
            
        except Exception as e:
            self.logger.error(f"Error logging business action: {e}")
    
    def format_response(
        self,
        code: int = 0,
        message: str = "",
        data: Any = None
    ) -> Dict[str, Any]:
        """
        格式化响应
        
        Args:
            code: 响应码，0表示成功
            message: 响应消息
            data: 响应数据
            
        Returns:
            格式化的响应字典
        """
        response = {
            "code": code,
            "message": message or ("success" if code == 0 else "error")
        }
        
        if data is not None:
            response["data"] = data
        
        return response
    
    def success_response(self, data: Any = None, message: str = "success") -> Dict[str, Any]:
        """
        成功响应
        
        Args:
            data: 响应数据
            message: 响应消息
            
        Returns:
            成功响应字典
        """
        return self.format_response(0, message, data)
    
    def error_response(self, message: str, code: int = -1, data: Any = None) -> Dict[str, Any]:
        """
        错误响应
        
        Args:
            message: 错误消息
            code: 错误码
            data: 错误数据
            
        Returns:
            错误响应字典
        """
        return self.format_response(code, message, data)
    
    async def health_check(self) -> dict:
        """
        服务健康检查
        
        Returns:
            健康检查结果
        """
        base_health = await super().health_check()
        
        base_health.update({
            "player_cache_size": len(self._player_cache),
            "config_cache_size": len(self._config_cache)
        })
        
        return base_health