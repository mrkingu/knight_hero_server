"""
统一的游戏服务基类
Unified Game Service Base Class

作者: mrkingu
日期: 2025-06-20
描述: 增强的游戏服务基类，提供缓存管理、性能监控、配置管理等通用功能
"""
from abc import ABC
from typing import Any, Optional, Dict, List
import time
import logging

from common.ioc import BaseService
from common.performance import performance_monitor, async_cached, ObjectPool
from common.exceptions import GameException, ValidationError


class BaseGameService(BaseService, ABC):
    """
    游戏服务基类
    
    提供统一的服务功能：
    - 缓存管理
    - 性能监控  
    - 配置管理
    - 事件发送
    - 业务日志记录
    - 响应格式化
    """
    
    def __init__(self):
        super().__init__()
        self._cache: Dict[str, Any] = {}
        self._config: Dict[str, Any] = {}
        self._metrics_prefix = self.__class__.__name__.lower().replace('service', '')
        self._event_handlers: Dict[str, List] = {}
        
        # 对象池（如果需要）
        self._object_pools: Dict[str, ObjectPool] = {}
        
    async def on_initialize(self):
        """初始化服务"""
        await super().on_initialize()
        
        # 加载服务配置
        await self._load_service_config()
        
        # 初始化缓存
        await self._initialize_cache()
        
        # 注册事件处理器
        await self._register_event_handlers()
        
        self.logger.info(f"{self._service_name} initialized successfully")
        
    async def _load_service_config(self) -> None:
        """
        加载服务配置
        
        子类可以重写此方法来加载特定的配置
        """
        # 默认配置
        self._config = {
            "cache_ttl": 300,  # 5分钟
            "max_cache_size": 1000,
            "enable_metrics": True,
            "enable_events": True
        }
        
        # 这里可以从配置管理器加载配置
        # config_manager = self.get_service("ConfigManager")
        # if config_manager:
        #     service_config = await config_manager.get_service_config(self._service_name)
        #     self._config.update(service_config)
        
    async def _initialize_cache(self) -> None:
        """初始化缓存"""
        # 清理过期缓存的任务可以在这里启动
        pass
        
    async def _register_event_handlers(self) -> None:
        """注册事件处理器"""
        # 子类可以重写此方法注册特定的事件处理器
        pass
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self._config.get(key, default)
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """
        从缓存获取数据
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或None
        """
        cache_entry = self._cache.get(key)
        if cache_entry is None:
            return None
        
        value, expire_time = cache_entry
        current_time = time.time()
        
        if current_time >= expire_time:
            # 缓存过期，删除
            del self._cache[key]
            return None
        
        return value
    
    async def cache_set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间(秒)，默认使用配置中的值
        """
        if ttl is None:
            ttl = self.get_config("cache_ttl", 300)
        
        expire_time = time.time() + ttl
        self._cache[key] = (value, expire_time)
        
        # 检查缓存大小限制
        max_size = self.get_config("max_cache_size", 1000)
        if len(self._cache) > max_size:
            await self._cleanup_cache()
    
    async def cache_delete(self, key: str):
        """删除缓存"""
        self._cache.pop(key, None)
    
    async def clear_cache(self, pattern: Optional[str] = None):
        """
        清理缓存
        
        Args:
            pattern: 键名模式，为None时清理所有缓存
        """
        if pattern is None:
            self._cache.clear()
        else:
            keys_to_delete = [key for key in self._cache.keys() if pattern in key]
            for key in keys_to_delete:
                del self._cache[key]
    
    async def _cleanup_cache(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        for key, (value, expire_time) in self._cache.items():
            if current_time >= expire_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        # 如果还是太多，删除最老的一些
        max_size = self.get_config("max_cache_size", 1000)
        if len(self._cache) > max_size:
            # 按过期时间排序，删除最老的
            items = sorted(self._cache.items(), key=lambda x: x[1][1])
            to_delete = len(self._cache) - max_size
            
            for i in range(to_delete):
                key = items[i][0]
                del self._cache[key]
    
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """
        记录性能指标
        
        Args:
            name: 指标名称
            value: 指标值
            tags: 标签
        """
        if not self.get_config("enable_metrics", True):
            return
        
        metric_name = f"{self._metrics_prefix}_{name}"
        performance_monitor.record(metric_name, value, tags)
    
    async def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        发送事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if not self.get_config("enable_events", True):
            return
        
        # 添加服务信息
        event_data = {
            "service": self._service_name,
            "timestamp": time.time(),
            "type": event_type,
            "data": data
        }
        
        # 调用事件处理器
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_data)
            except Exception as e:
                self.logger.error(f"Event handler error: {e}")
        
        # 这里可以发送到事件总线
        # event_bus = self.get_service("EventBus")
        # if event_bus:
        #     await event_bus.publish(event_type, event_data)
    
    def subscribe_event(self, event_type: str, handler):
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理器
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def log_business_action(
        self,
        player_id: str,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """
        记录业务操作日志
        
        Args:
            player_id: 玩家ID
            action: 操作类型
            params: 操作参数
            result: 操作结果
        """
        log_data = {
            "service": self._service_name,
            "player_id": player_id,
            "action": action,
            "params": params,
            "result": result,
            "timestamp": time.time()
        }
        
        # 记录到业务日志
        business_logger = logging.getLogger(f"business.{self._service_name}")
        business_logger.info(f"Action: {action}, Player: {player_id}, Result: {result.get('code', 'unknown')}")
        
        # 发送业务事件
        await self.emit_event("business_action", log_data)
    
    def format_response(
        self,
        code: int = 0,
        message: str = "",
        data: Any = None
    ) -> Dict[str, Any]:
        """
        格式化响应
        
        Args:
            code: 响应码
            message: 响应消息
            data: 响应数据
            
        Returns:
            格式化的响应字典
        """
        response = {
            "code": code,
            "message": message,
            "timestamp": int(time.time())
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
    
    def validate_params(self, params: Dict[str, Any], required_fields: List[str]) -> None:
        """
        验证参数
        
        Args:
            params: 参数字典
            required_fields: 必需字段列表
            
        Raises:
            ValidationError: 参数验证失败
        """
        missing_fields = []
        
        for field in required_fields:
            if field not in params or params[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    
    def validate_numeric_range(
        self, 
        value: Any, 
        field_name: str, 
        min_value: Optional[int] = None, 
        max_value: Optional[int] = None
    ) -> int:
        """
        验证数值范围
        
        Args:
            value: 要验证的值
            field_name: 字段名
            min_value: 最小值
            max_value: 最大值
            
        Returns:
            验证后的整数值
            
        Raises:
            ValidationError: 验证失败
        """
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be a valid number")
        
        if min_value is not None and int_value < min_value:
            raise ValidationError(f"{field_name} must be >= {min_value}")
        
        if max_value is not None and int_value > max_value:
            raise ValidationError(f"{field_name} must be <= {max_value}")
        
        return int_value
    
    def get_object_pool(self, pool_name: str, factory, size: int = 100) -> ObjectPool:
        """
        获取对象池
        
        Args:
            pool_name: 池名称
            factory: 对象工厂函数
            size: 池大小
            
        Returns:
            对象池实例
        """
        if pool_name not in self._object_pools:
            self._object_pools[pool_name] = ObjectPool(factory, size)
        
        return self._object_pools[pool_name]
    
    async def health_check(self) -> dict:
        """
        服务健康检查
        
        Returns:
            健康检查结果
        """
        base_health = await super().health_check()
        
        # 添加服务特定的健康信息
        base_health.update({
            "cache_size": len(self._cache),
            "max_cache_size": self.get_config("max_cache_size", 1000),
            "config_loaded": bool(self._config),
            "metrics_enabled": self.get_config("enable_metrics", True),
            "events_enabled": self.get_config("enable_events", True),
            "event_handlers": {
                event_type: len(handlers) 
                for event_type, handlers in self._event_handlers.items()
            },
            "object_pools": {
                name: pool.get_stats() 
                for name, pool in self._object_pools.items()
            }
        })
        
        return base_health
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息
        
        Returns:
            性能统计数据
        """
        all_metrics = performance_monitor.get_metrics()
        
        # 筛选出本服务的指标
        service_metrics = {
            name: metric for name, metric in all_metrics.items()
            if name.startswith(self._metrics_prefix)
        }
        
        return {
            "service": self._service_name,
            "metrics": service_metrics,
            "cache_stats": {
                "size": len(self._cache),
                "max_size": self.get_config("max_cache_size", 1000)
            },
            "pool_stats": {
                name: pool.get_stats() 
                for name, pool in self._object_pools.items()
            }
        }
    
    async def on_shutdown(self):
        """服务关闭时的清理"""
        # 清理缓存
        self._cache.clear()
        
        # 清理对象池
        for pool in self._object_pools.values():
            # 对象池的清理逻辑
            pass
        
        await super().on_shutdown()