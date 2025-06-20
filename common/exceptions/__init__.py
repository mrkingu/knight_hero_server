"""
统一的异常定义
Unified Exception Definitions

作者: mrkingu
日期: 2025-06-20
描述: 替代分散的错误处理，提供统一的异常体系
"""
from typing import Any, Optional


class GameException(Exception):
    """游戏异常基类"""
    
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result


class ValidationError(GameException):
    """参数验证错误"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        data = {"field": field} if field else None
        super().__init__(code=400, message=message, data=data)


class BusinessError(GameException):
    """业务逻辑错误"""
    
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(code=code, message=message, data=data)


class AuthenticationError(GameException):
    """认证错误"""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(code=401, message=message)


class AuthorizationError(GameException):
    """授权错误"""
    
    def __init__(self, message: str = "Access denied"):
        super().__init__(code=403, message=message)


class ResourceNotFoundError(GameException):
    """资源不存在"""
    
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code=404,
            message=f"{resource} not found: {resource_id}",
            data={"resource": resource, "resource_id": resource_id}
        )


class ConflictError(GameException):
    """资源冲突错误"""
    
    def __init__(self, message: str, data: Any = None):
        super().__init__(code=409, message=message, data=data)


class InsufficientResourceError(ConflictError):
    """资源不足"""
    
    def __init__(self, resource: str, required: int, current: int):
        super().__init__(
            message=f"Insufficient {resource}: required {required}, current {current}",
            data={
                "resource": resource,
                "required": required,
                "current": current,
                "shortage": required - current
            }
        )


class RateLimitError(GameException):
    """频率限制错误"""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        data = {"retry_after": retry_after} if retry_after else None
        super().__init__(code=429, message=message, data=data)


class ServerError(GameException):
    """服务器内部错误"""
    
    def __init__(self, message: str = "Internal server error", data: Any = None):
        super().__init__(code=500, message=message, data=data)


class ServiceUnavailableError(GameException):
    """服务不可用错误"""
    
    def __init__(self, service: str, message: Optional[str] = None):
        message = message or f"Service unavailable: {service}"
        super().__init__(
            code=503,
            message=message,
            data={"service": service}
        )


class TimeoutError(GameException):
    """超时错误"""
    
    def __init__(self, operation: str, timeout: float):
        super().__init__(
            code=504,
            message=f"Operation timeout: {operation}",
            data={"operation": operation, "timeout": timeout}
        )


# 错误码定义
class ErrorCode:
    """统一错误码"""
    
    # 成功
    SUCCESS = 0
    
    # 客户端错误 (4xx)
    INVALID_PARAMS = 400
    MISSING_PARAMS = 401
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    RATE_LIMITED = 429
    
    # 服务器错误 (5xx)
    SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    SERVICE_UNAVAILABLE = 503
    TIMEOUT = 504
    
    # 业务错误 (1000+)
    PLAYER_NOT_FOUND = 1001
    PLAYER_ALREADY_EXISTS = 1002
    INSUFFICIENT_DIAMOND = 1003
    INSUFFICIENT_ENERGY = 1004
    LEVEL_MAX_REACHED = 1005
    ITEM_NOT_FOUND = 1006
    ITEM_INSUFFICIENT = 1007
    
    # 游戏逻辑错误 (2000+)
    BATTLE_NOT_FOUND = 2001
    BATTLE_ALREADY_ENDED = 2002
    SKILL_COOLDOWN = 2003
    SKILL_NOT_LEARNED = 2004
    EQUIPMENT_NOT_SUITABLE = 2005
    
    # 聊天相关错误 (3000+)
    CHANNEL_NOT_FOUND = 3001
    MESSAGE_TOO_LONG = 3002
    BANNED_FROM_CHANNEL = 3003
    SPAM_DETECTED = 3004


# 预定义的业务异常
class PlayerNotFoundError(ResourceNotFoundError):
    """玩家不存在异常"""
    
    def __init__(self, player_id: str):
        super().__init__("Player", player_id)


class PlayerAlreadyExistsError(ConflictError):
    """玩家已存在异常"""
    
    def __init__(self, player_id: str):
        super().__init__(
            f"Player already exists: {player_id}",
            data={"player_id": player_id}
        )


class InsufficientDiamondError(InsufficientResourceError):
    """钻石不足异常"""
    
    def __init__(self, required: int, current: int):
        super().__init__("diamond", required, current)


class InsufficientEnergyError(InsufficientResourceError):
    """体力不足异常"""
    
    def __init__(self, required: int, current: int):
        super().__init__("energy", required, current)


class ItemNotFoundError(ResourceNotFoundError):
    """物品不存在异常"""
    
    def __init__(self, item_id: str):
        super().__init__("Item", item_id)


class SkillCooldownError(BusinessError):
    """技能冷却中异常"""
    
    def __init__(self, skill_id: str, remaining_time: int):
        super().__init__(
            code=ErrorCode.SKILL_COOLDOWN,
            message=f"Skill {skill_id} is on cooldown",
            data={"skill_id": skill_id, "remaining_time": remaining_time}
        )


class BattleNotFoundError(ResourceNotFoundError):
    """战斗不存在异常"""
    
    def __init__(self, battle_id: str):
        super().__init__("Battle", battle_id)


class ChannelNotFoundError(ResourceNotFoundError):
    """频道不存在异常"""
    
    def __init__(self, channel_id: str):
        super().__init__("Channel", channel_id)


def create_error_response(exception: GameException) -> dict:
    """
    创建标准错误响应
    
    Args:
        exception: 游戏异常对象
        
    Returns:
        标准错误响应字典
    """
    import time
    
    response = {
        "code": exception.code,
        "message": exception.message,
        "timestamp": int(time.time())
    }
    
    if exception.data is not None:
        response["data"] = exception.data
    
    return response


def handle_exception(func):
    """
    异常处理装饰器
    
    自动捕获并转换异常为标准响应格式
    """
    import functools
    import logging
    
    logger = logging.getLogger(func.__module__)
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except GameException as e:
            logger.warning(f"Business exception in {func.__name__}: {e}")
            return create_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected exception in {func.__name__}: {e}", exc_info=True)
            server_error = ServerError("Internal server error")
            return create_error_response(server_error)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except GameException as e:
            logger.warning(f"Business exception in {func.__name__}: {e}")
            return create_error_response(e)
        except Exception as e:
            logger.error(f"Unexpected exception in {func.__name__}: {e}", exc_info=True)
            server_error = ServerError("Internal server error")
            return create_error_response(server_error)
    
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper