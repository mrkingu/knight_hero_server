"""
Handler基类 - IoC版本
Base Handler Class with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 支持依赖注入的Handler基类，只负责参数解析和响应封装，业务逻辑委托给Service层
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging
import time
import traceback

from common.ioc import BaseService

logger = logging.getLogger(__name__)


class BaseHandler(BaseService, ABC):
    """
    Handler基类 - 支持IoC
    
    处理请求参数解析和响应封装，业务逻辑委托给Service层
    """
    
    def __init__(self):
        """初始化Handler"""
        super().__init__()
        self._request_count = 0
        self._error_count = 0
        self._total_time = 0.0
    
    async def on_initialize(self) -> None:
        """初始化Handler"""
        await super().on_initialize()
        self.logger.info(f"Handler initialized: {self._service_name}")
    
    async def handle_request(self, request: dict) -> dict:
        """
        统一的请求处理流程
        
        Args:
            request: 请求数据
            
        Returns:
            响应数据
        """
        start_time = time.time()
        self._request_count += 1
        
        try:
            # 1. 解析参数
            params = await self.parse_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_params(params)
            if not validation_result.get("valid", False):
                self._error_count += 1
                return self.error_response(validation_result.get("reason", "Invalid parameters"))
            
            # 3. 调用业务处理
            result = await self.process_business(params)
            
            # 4. 封装响应
            if isinstance(result, dict) and "code" in result:
                # 已经是格式化的响应
                response = result
            else:
                # 包装为成功响应
                response = self.success_response(result)
            
            # 5. 记录统计
            self._total_time += time.time() - start_time
            
            return response
            
        except Exception as e:
            self._error_count += 1
            self.logger.error(f"Handle request error: {e}\n{traceback.format_exc()}")
            return self.error_response(f"Internal error: {str(e)}")
    
    @abstractmethod
    async def parse_params(self, request: dict) -> dict:
        """
        解析请求参数
        
        Args:
            request: 原始请求数据
            
        Returns:
            解析后的参数字典
        """
        pass
    
    @abstractmethod
    async def validate_params(self, params: dict) -> dict:
        """
        验证参数
        
        Args:
            params: 解析后的参数
            
        Returns:
            验证结果 {"valid": bool, "reason": str}
        """
        pass
    
    @abstractmethod
    async def process_business(self, params: dict) -> Any:
        """
        处理业务逻辑
        
        Args:
            params: 验证后的参数
            
        Returns:
            业务处理结果
        """
        pass
    
    def success_response(self, data: Any = None, message: str = "success") -> dict:
        """
        成功响应
        
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
    
    def error_response(self, message: str, code: int = -1, data: Any = None) -> dict:
        """
        错误响应
        
        Args:
            message: 错误消息
            code: 错误码
            data: 错误数据
            
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
    
    def extract_player_id(self, request: dict) -> Optional[str]:
        """
        从请求中提取玩家ID
        
        Args:
            request: 请求数据
            
        Returns:
            玩家ID
        """
        # 常见的玩家ID字段名
        player_id_fields = ["player_id", "playerId", "user_id", "userId"]
        
        for field in player_id_fields:
            if field in request:
                return str(request[field])
        
        # 从token或session中提取
        token = request.get("token") or request.get("session_token")
        if token:
            # 这里应该通过认证服务解析token获取玩家ID
            # 暂时简化处理
            if token.startswith("token_"):
                parts = token.split("_")
                if len(parts) >= 2:
                    return parts[1]
        
        return None
    
    def validate_required_params(self, params: dict, required_fields: list) -> dict:
        """
        验证必需参数
        
        Args:
            params: 参数字典
            required_fields: 必需字段列表
            
        Returns:
            验证结果
        """
        missing_fields = []
        
        for field in required_fields:
            if field not in params or params[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            return {
                "valid": False,
                "reason": f"Missing required fields: {', '.join(missing_fields)}"
            }
        
        return {"valid": True}
    
    def validate_numeric_params(self, params: dict, numeric_fields: dict) -> dict:
        """
        验证数值参数
        
        Args:
            params: 参数字典
            numeric_fields: 数值字段配置 {field: {"min": 0, "max": 1000}}
            
        Returns:
            验证结果
        """
        for field, config in numeric_fields.items():
            if field not in params:
                continue
            
            try:
                value = int(params[field])
                params[field] = value  # 转换为整数
                
                if "min" in config and value < config["min"]:
                    return {
                        "valid": False,
                        "reason": f"{field} must be >= {config['min']}"
                    }
                
                if "max" in config and value > config["max"]:
                    return {
                        "valid": False,
                        "reason": f"{field} must be <= {config['max']}"
                    }
                
            except (ValueError, TypeError):
                return {
                    "valid": False,
                    "reason": f"{field} must be a valid number"
                }
        
        return {"valid": True}
    
    async def health_check(self) -> dict:
        """
        Handler健康检查
        
        Returns:
            健康检查结果
        """
        base_health = await super().health_check()
        
        avg_time = self._total_time / self._request_count if self._request_count > 0 else 0
        error_rate = self._error_count / self._request_count if self._request_count > 0 else 0
        
        base_health.update({
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": error_rate,
            "avg_response_time": avg_time
        })
        
        return base_health
    
    def get_stats(self) -> dict:
        """
        获取Handler统计信息
        
        Returns:
            统计信息
        """
        return {
            "handler_name": self._service_name,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "total_time": self._total_time,
            "avg_time": self._total_time / self._request_count if self._request_count > 0 else 0,
            "error_rate": self._error_count / self._request_count if self._request_count > 0 else 0
        }