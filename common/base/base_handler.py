"""
统一的Handler基类
Unified Base Handler Class

作者: mrkingu
日期: 2025-06-20
描述: 统一的请求处理器基类，提供标准化的请求处理流程，所有请求处理器的基类
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TypeVar, Generic
import logging
import time
import traceback

from common.ioc import BaseService
from common.exceptions import ValidationError, BusinessError

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class BaseHandler(BaseService, ABC, Generic[T, R]):
    """
    请求处理器基类
    
    提供统一的请求处理流程：
    1. 请求日志记录
    2. 参数验证  
    3. 前置处理钩子
    4. 业务逻辑处理
    5. 后置处理钩子
    6. 响应日志记录
    7. 统一异常处理
    """
    
    def __init__(self):
        super().__init__()
        self._request_count = 0
        self._error_count = 0
        self._total_time = 0.0
        self._success_count = 0
        
    async def on_initialize(self):
        """初始化Handler"""
        await super().on_initialize()
        self.logger.info(f"Handler initialized: {self._service_name}")
        
    async def handle(self, request: T) -> R:
        """
        统一的请求处理流程
        
        Args:
            request: 请求对象
            
        Returns:
            响应对象
            
        Raises:
            ValidationError: 参数验证失败
            BusinessError: 业务逻辑错误
        """
        start_time = time.time()
        self._request_count += 1
        
        try:
            # 1. 请求日志
            self.logger.debug(f"Handling request: {self._service_name}")
            
            # 2. 参数验证
            validated_request = await self.validate(request)
            
            # 3. 前置处理
            await self.before_process(validated_request)
            
            # 4. 业务处理
            result = await self.process(validated_request)
            
            # 5. 后置处理
            response = await self.after_process(result)
            
            # 6. 响应日志
            elapsed_time = time.time() - start_time
            self._total_time += elapsed_time
            self._success_count += 1
            
            self.logger.debug(f"Request processed successfully in {elapsed_time:.3f}s")
            
            return response
            
        except ValidationError as e:
            self._error_count += 1
            self.logger.warning(f"Validation error: {e}")
            return self.error_response(code=e.code, message=str(e))
            
        except BusinessError as e:
            self._error_count += 1
            self.logger.warning(f"Business error: {e}")
            return self.error_response(code=e.code, message=e.message)
            
        except Exception as e:
            self._error_count += 1
            self.logger.error(f"Unexpected error: {e}", exc_info=True)
            return self.error_response(code=ErrorCode.SERVER_ERROR, message="Internal server error")
    
    @abstractmethod
    async def validate(self, request: T) -> T:
        """
        验证请求参数
        
        Args:
            request: 原始请求
            
        Returns:
            验证后的请求对象
            
        Raises:
            ValidationError: 验证失败
        """
        pass
        
    async def before_process(self, request: T) -> None:
        """
        前置处理钩子
        
        子类可以重写此方法进行预处理，如权限检查、限流等
        
        Args:
            request: 验证后的请求对象
        """
        pass
        
    @abstractmethod
    async def process(self, request: T) -> Any:
        """
        处理业务逻辑
        
        Args:
            request: 验证后的请求对象
            
        Returns:
            处理结果
        """
        pass
        
    async def after_process(self, result: Any) -> R:
        """
        后置处理钩子
        
        子类可以重写此方法进行后处理，如结果转换、缓存更新等
        
        Args:
            result: 业务处理结果
            
        Returns:
            最终响应对象
        """
        return self.success_response(result)
        
    @abstractmethod
    def success_response(self, data: Any) -> R:
        """
        构建成功响应
        
        Args:
            data: 响应数据
            
        Returns:
            成功响应对象
        """
        pass
        
    @abstractmethod
    def error_response(self, code: int, message: str) -> R:
        """
        构建错误响应
        
        Args:
            code: 错误码
            message: 错误信息
            
        Returns:
            错误响应对象
        """
        pass
    
    def extract_player_id(self, request: Dict[str, Any]) -> Optional[str]:
        """
        从请求中提取玩家ID
        
        Args:
            request: 请求数据
            
        Returns:
            玩家ID，如果未找到返回None
        """
        # 常见的玩家ID字段名
        player_id_fields = ["player_id", "playerId", "user_id", "userId"]
        
        for field in player_id_fields:
            if field in request:
                return str(request[field])
        
        # 从token或session中提取
        token = request.get("token") or request.get("session_token")
        if token:
            # 解析token获取玩家ID
            if token.startswith("token_"):
                parts = token.split("_")
                if len(parts) >= 2:
                    return parts[1]
        
        return None
    
    def validate_required_params(self, params: Dict[str, Any], required_fields: list) -> None:
        """
        验证必需参数
        
        Args:
            params: 参数字典
            required_fields: 必需字段列表
            
        Raises:
            ValidationError: 缺少必需参数
        """
        missing_fields = []
        
        for field in required_fields:
            if field not in params or params[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
    
    def validate_numeric_params(
        self, 
        params: Dict[str, Any], 
        numeric_fields: Dict[str, Dict[str, int]]
    ) -> None:
        """
        验证数值参数
        
        Args:
            params: 参数字典
            numeric_fields: 数值字段配置 {field: {"min": 0, "max": 1000}}
            
        Raises:
            ValidationError: 数值验证失败
        """
        for field, config in numeric_fields.items():
            if field not in params:
                continue
            
            try:
                value = int(params[field])
                params[field] = value  # 转换为整数
                
                if "min" in config and value < config["min"]:
                    raise ValidationError(f"{field} must be >= {config['min']}")
                
                if "max" in config and value > config["max"]:
                    raise ValidationError(f"{field} must be <= {config['max']}")
                
            except (ValueError, TypeError):
                raise ValidationError(f"{field} must be a valid number")
    
    def sanitize_string(self, text: str, max_length: int = 1000) -> str:
        """
        清理字符串输入
        
        Args:
            text: 输入文本
            max_length: 最大长度
            
        Returns:
            清理后的文本
        """
        if not isinstance(text, str):
            text = str(text)
        
        # 移除前后空白
        text = text.strip()
        
        # 限制长度
        if len(text) > max_length:
            text = text[:max_length]
        
        # 移除控制字符
        text = "".join(char for char in text if ord(char) >= 32 or char in ['\n', '\t'])
        
        return text
    
    async def health_check(self) -> dict:
        """
        Handler健康检查
        
        Returns:
            健康检查结果
        """
        base_health = await super().health_check()
        
        avg_time = self._total_time / self._request_count if self._request_count > 0 else 0
        error_rate = self._error_count / self._request_count if self._request_count > 0 else 0
        success_rate = self._success_count / self._request_count if self._request_count > 0 else 0
        
        base_health.update({
            "handler_name": self._service_name,
            "request_count": self._request_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "avg_response_time": avg_time,
            "total_processing_time": self._total_time
        })
        
        return base_health
    
    def get_stats(self) -> dict:
        """
        获取Handler统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "handler_name": self._service_name,
            "request_count": self._request_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "total_time": self._total_time,
            "avg_time": self._total_time / self._request_count if self._request_count > 0 else 0,
            "success_rate": self._success_count / self._request_count if self._request_count > 0 else 0,
            "error_rate": self._error_count / self._request_count if self._request_count > 0 else 0
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_time = 0.0


class DictHandler(BaseHandler[Dict[str, Any], Dict[str, Any]]):
    """
    处理字典类型请求的Handler基类
    
    大多数HTTP/WebSocket请求可以继承此类
    """
    
    def success_response(self, data: Any = None, message: str = "success") -> Dict[str, Any]:
        """
        构建成功响应
        
        Args:
            data: 响应数据
            message: 响应消息
            
        Returns:
            成功响应字典
        """
        response = {
            "code": 0,
            "message": message,
            "timestamp": int(time.time())
        }
        
        if data is not None:
            response["data"] = data
        
        return response
    
    def error_response(self, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """
        构建错误响应
        
        Args:
            code: 错误码
            message: 错误信息
            data: 错误相关数据
            
        Returns:
            错误响应字典
        """
        response = {
            "code": code,
            "message": message,
            "timestamp": int(time.time())
        }
        
        if data is not None:
            response["data"] = data
        
        return response