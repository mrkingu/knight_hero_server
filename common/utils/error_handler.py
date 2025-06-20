"""
统一错误处理工具
作者: lx
日期: 2025-06-20
"""
import logging
import traceback
from typing import Any, Dict, Optional, Type, Callable
from functools import wraps

class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def handle_error(
        self, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None,
        reraise: bool = True
    ) -> Dict[str, Any]:
        """
        处理错误
        
        Args:
            error: 异常对象
            context: 上下文信息
            reraise: 是否重新抛出异常
            
        Returns:
            错误信息字典
        """
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context or {}
        }
        
        # 记录错误日志
        self.logger.error(
            f"Error occurred: {error_info['error_type']} - {error_info['error_message']}",
            extra={"error_info": error_info}
        )
        
        if reraise:
            raise error
            
        return error_info
    
    def wrap_function(self, func: Callable) -> Callable:
        """
        包装函数以自动处理错误
        
        Args:
            func: 要包装的函数
            
        Returns:
            包装后的函数
        """
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return self.handle_error(e, {"function": func.__name__, "args": args, "kwargs": kwargs})
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return self.handle_error(e, {"function": func.__name__, "args": args, "kwargs": kwargs})
        
        # 检查是否是异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

def handle_errors(reraise: bool = True):
    """
    错误处理装饰器
    
    Args:
        reraise: 是否重新抛出异常
    """
    def decorator(func: Callable) -> Callable:
        handler = ErrorHandler()
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return handler.handle_error(
                    e, 
                    {"function": func.__name__, "args": args, "kwargs": kwargs},
                    reraise=reraise
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return handler.handle_error(
                    e,
                    {"function": func.__name__, "args": args, "kwargs": kwargs}, 
                    reraise=reraise
                )
        
        # 检查是否是异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

# 全局错误处理器实例
_global_error_handler: Optional[ErrorHandler] = None

def get_error_handler() -> ErrorHandler:
    """获取全局错误处理器实例"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler

__all__ = ['ErrorHandler', 'handle_errors', 'get_error_handler']