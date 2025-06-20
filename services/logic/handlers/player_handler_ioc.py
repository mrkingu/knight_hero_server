"""
玩家请求处理器 - IoC版本
Player Handler with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 只负责参数解析和响应封装，业务逻辑委托给PlayerService
"""

from typing import Dict, Any
import logging

from common.ioc import service, autowired
from ..handlers.base.base_handler_ioc import BaseHandler

logger = logging.getLogger(__name__)


@service("PlayerHandler")
class PlayerHandler(BaseHandler):
    """
    玩家请求处理器
    
    负责处理玩家相关的HTTP/gRPC请求，包括：
    - 登录请求
    - 玩家信息查询
    - 资源操作请求
    - 等级经验请求
    """
    
    @autowired("PlayerService")
    def player_service(self):
        """玩家服务 - 自动注入"""
        pass
    
    async def on_initialize(self) -> None:
        """初始化Handler"""
        await super().on_initialize()
        self.logger.info("PlayerHandler initialized")
    
    async def handle_login(self, request: dict) -> dict:
        """
        处理登录请求
        
        Args:
            request: 登录请求数据
            
        Returns:
            登录响应
        """
        try:
            # 1. 解析参数
            params = await self.parse_login_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_login_params(params)
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 3. 委托给Service处理业务逻辑
            # 生成玩家ID（简化处理）
            player_id = f"player_{params['username']}"
            
            # 获取或创建玩家
            player_result = await self.player_service.get_or_create_player(
                player_id,
                nickname=params['username']
            )
            
            if player_result["code"] != 0:
                return player_result
            
            # 更新登录信息
            login_result = await self.player_service.update_login_info(player_id)
            
            # 恢复体力
            energy_result = await self.player_service.recover_energy(player_id)
            
            # 组装登录响应
            response_data = {
                "player_id": player_id,
                "token": f"token_{player_id}_{int(__import__('time').time())}",
                "server_time": int(__import__('time').time()),
                "player_info": player_result["data"],
                "login_reward": login_result.get("data", {}).get("login_reward", 0),
                "is_daily_first": login_result.get("data", {}).get("is_daily_first", False)
            }
            
            return self.success_response(response_data, "Login successful")
            
        except Exception as e:
            self.logger.error(f"Login error: {e}")
            return self.error_response(f"Login failed: {e}")
    
    async def handle_get_player_info(self, request: dict) -> dict:
        """
        处理获取玩家信息请求
        
        Args:
            request: 请求数据
            
        Returns:
            玩家信息响应
        """
        try:
            # 1. 解析参数
            params = await self.parse_get_info_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_get_info_params(params)
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 3. 委托给Service处理
            result = await self.player_service.get_player_info(params["player_id"])
            
            return result
            
        except Exception as e:
            self.logger.error(f"Get player info error: {e}")
            return self.error_response(f"Failed to get player info: {e}")
    
    async def handle_add_diamond(self, request: dict) -> dict:
        """
        处理增加钻石请求
        
        Args:
            request: 请求数据
            
        Returns:
            操作结果
        """
        try:
            # 1. 解析参数
            params = await self.parse_add_diamond_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_add_diamond_params(params)
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 3. 委托给Service处理
            result = await self.player_service.add_diamond(
                params["player_id"],
                params["amount"],
                params["source"],
                params.get("order_id")
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Add diamond error: {e}")
            return self.error_response(f"Failed to add diamond: {e}")
    
    async def handle_consume_diamond(self, request: dict) -> dict:
        """
        处理消耗钻石请求
        
        Args:
            request: 请求数据
            
        Returns:
            操作结果
        """
        try:
            # 1. 解析参数
            params = await self.parse_consume_diamond_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_consume_diamond_params(params)
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 3. 委托给Service处理
            result = await self.player_service.consume_diamond(
                params["player_id"],
                params["amount"],
                params["source"]
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Consume diamond error: {e}")
            return self.error_response(f"Failed to consume diamond: {e}")
    
    async def handle_add_experience(self, request: dict) -> dict:
        """
        处理增加经验请求
        
        Args:
            request: 请求数据
            
        Returns:
            操作结果
        """
        try:
            # 1. 解析参数
            params = await self.parse_add_exp_params(request)
            
            # 2. 参数验证
            validation_result = await self.validate_add_exp_params(params)
            if not validation_result["valid"]:
                return self.error_response(validation_result["reason"])
            
            # 3. 委托给Service处理
            result = await self.player_service.add_experience(
                params["player_id"],
                params["exp"],
                params["source"]
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Add experience error: {e}")
            return self.error_response(f"Failed to add experience: {e}")
    
    # 实现抽象方法 - 通用处理
    async def parse_params(self, request: dict) -> dict:
        """解析通用请求参数"""
        # 提取基础参数
        params = {
            "action": request.get("action", ""),
            "player_id": self.extract_player_id(request)
        }
        
        # 合并其他参数
        params.update(request)
        
        return params
    
    async def validate_params(self, params: dict) -> dict:
        """验证通用参数"""
        # 基础验证
        if not params.get("action"):
            return {"valid": False, "reason": "Missing action parameter"}
        
        return {"valid": True}
    
    async def process_business(self, params: dict) -> Any:
        """根据action分发到具体的处理方法"""
        action = params.get("action", "")
        
        if action == "login":
            return await self.handle_login(params)
        elif action == "get_info":
            return await self.handle_get_player_info(params)
        elif action == "add_diamond":
            return await self.handle_add_diamond(params)
        elif action == "consume_diamond":
            return await self.handle_consume_diamond(params)
        elif action == "add_experience":
            return await self.handle_add_experience(params)
        else:
            return self.error_response(f"Unknown action: {action}")
    
    # 具体的参数解析方法
    async def parse_login_params(self, request: dict) -> dict:
        """解析登录参数"""
        return {
            "username": request.get("username", ""),
            "password": request.get("password", ""),
            "device_id": request.get("device_id", ""),
            "version": request.get("version", "")
        }
    
    async def validate_login_params(self, params: dict) -> dict:
        """验证登录参数"""
        # 检查必需参数
        required_result = self.validate_required_params(params, ["username", "password"])
        if not required_result["valid"]:
            return required_result
        
        # 验证用户名长度
        if len(params["username"]) < 3 or len(params["username"]) > 20:
            return {"valid": False, "reason": "Username must be 3-20 characters"}
        
        # 验证密码
        if len(params["password"]) < 1:
            return {"valid": False, "reason": "Password cannot be empty"}
        
        return {"valid": True}
    
    async def parse_get_info_params(self, request: dict) -> dict:
        """解析获取玩家信息参数"""
        return {
            "player_id": self.extract_player_id(request) or request.get("target_player_id", "")
        }
    
    async def validate_get_info_params(self, params: dict) -> dict:
        """验证获取玩家信息参数"""
        return self.validate_required_params(params, ["player_id"])
    
    async def parse_add_diamond_params(self, request: dict) -> dict:
        """解析增加钻石参数"""
        return {
            "player_id": self.extract_player_id(request),
            "amount": request.get("amount", 0),
            "source": request.get("source", "unknown"),
            "order_id": request.get("order_id")
        }
    
    async def validate_add_diamond_params(self, params: dict) -> dict:
        """验证增加钻石参数"""
        # 检查必需参数
        required_result = self.validate_required_params(params, ["player_id", "amount", "source"])
        if not required_result["valid"]:
            return required_result
        
        # 验证数值参数
        numeric_result = self.validate_numeric_params(params, {
            "amount": {"min": 1, "max": 999999}
        })
        if not numeric_result["valid"]:
            return numeric_result
        
        return {"valid": True}
    
    async def parse_consume_diamond_params(self, request: dict) -> dict:
        """解析消耗钻石参数"""
        return {
            "player_id": self.extract_player_id(request),
            "amount": request.get("amount", 0),
            "source": request.get("source", "unknown")
        }
    
    async def validate_consume_diamond_params(self, params: dict) -> dict:
        """验证消耗钻石参数"""
        # 检查必需参数
        required_result = self.validate_required_params(params, ["player_id", "amount", "source"])
        if not required_result["valid"]:
            return required_result
        
        # 验证数值参数
        numeric_result = self.validate_numeric_params(params, {
            "amount": {"min": 1, "max": 999999}
        })
        if not numeric_result["valid"]:
            return numeric_result
        
        return {"valid": True}
    
    async def parse_add_exp_params(self, request: dict) -> dict:
        """解析增加经验参数"""
        return {
            "player_id": self.extract_player_id(request),
            "exp": request.get("exp", 0),
            "source": request.get("source", "unknown")
        }
    
    async def validate_add_exp_params(self, params: dict) -> dict:
        """验证增加经验参数"""
        # 检查必需参数
        required_result = self.validate_required_params(params, ["player_id", "exp", "source"])
        if not required_result["valid"]:
            return required_result
        
        # 验证数值参数
        numeric_result = self.validate_numeric_params(params, {
            "exp": {"min": 1, "max": 999999}
        })
        if not numeric_result["valid"]:
            return numeric_result
        
        return {"valid": True}