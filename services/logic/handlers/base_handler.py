"""
Handler基类模块
Base Handler Module

作者: lx  
日期: 2025-06-20
描述: 提供Handler基类和@handler装饰器，用于请求路由和处理
"""

from typing import Dict, Any, Callable, Optional, Type
from functools import wraps
import asyncio
import logging
import time
from datetime import datetime

from common.protocol.core.message_type import MessageType
from common.protocol.core.base_request import BaseRequest
from common.protocol.core.base_response import BaseResponse

logger = logging.getLogger(__name__)

# 全局处理器注册表
HANDLER_REGISTRY: Dict[int, Callable] = {}


def handler(cmd: int):
    """
    Handler装饰器，用于注册消息处理器
    
    Args:
        cmd: 消息号
        
    Usage:
        @handler(cmd=1001)
        async def handle_login(self, req: LoginRequest) -> LoginResponse:
            pass
    """
    def decorator(func: Callable) -> Callable:
        # 注册到全局注册表
        if cmd in HANDLER_REGISTRY:
            raise ValueError(f"Handler for command {cmd} already registered")
        HANDLER_REGISTRY[cmd] = func
        
        @wraps(func)
        async def wrapper(self, request: BaseRequest, *args, **kwargs):
            """处理器包装器，提供统一的前后处理逻辑"""
            start_time = time.time()
            
            try:
                # 请求验证
                if not await self._validate_request(request):
                    return self._create_error_response(
                        request, 400, "请求验证失败"
                    )
                
                # 执行业务逻辑
                response = await func(self, request, *args, **kwargs)
                
                # 响应后处理
                await self._post_process(request, response, start_time)
                
                return response
                
            except Exception as e:
                logger.error(f"Handler执行异常 cmd={cmd}: {e}", exc_info=True)
                return self._create_error_response(
                    request, 500, f"服务器内部错误: {str(e)}"
                )
        
        # 保存命令号信息
        wrapper._handler_cmd = cmd
        wrapper._original_func = func
        
        return wrapper
    
    return decorator


class BaseHandler:
    """Handler基类"""
    
    def __init__(self):
        """初始化处理器"""
        self.start_time = datetime.now()
        
    async def _validate_request(self, request: BaseRequest) -> bool:
        """
        验证请求
        
        Args:
            request: 请求对象
            
        Returns:
            是否有效
        """
        if not request:
            return False
            
        # 检查请求是否有验证方法并调用
        if hasattr(request, 'validate') and callable(request.validate):
            return request.validate()
            
        return True
    
    def _create_error_response(
        self, 
        request: BaseRequest, 
        code: int, 
        message: str
    ) -> BaseResponse:
        """
        创建错误响应
        
        Args:
            request: 原始请求
            code: 错误码
            message: 错误信息
            
        Returns:
            错误响应对象
        """
        # 获取对应的响应类型
        response_type = MessageType.get_response_type(request.MESSAGE_TYPE)
        
        # 创建基础响应对象
        response = BaseResponse()
        response.MESSAGE_TYPE = response_type
        response.code = code
        response.message = message
        response.timestamp = int(time.time())
        
        return response
    
    async def _post_process(
        self, 
        request: BaseRequest, 
        response: BaseResponse, 
        start_time: float
    ) -> None:
        """
        响应后处理
        
        Args:
            request: 请求对象
            response: 响应对象
            start_time: 开始时间
        """
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 记录处理日志
        logger.info(
            f"处理完成 cmd={request.MESSAGE_TYPE} "
            f"code={response.code} time={process_time:.3f}s"
        )
        
        # 设置响应时间戳
        if not hasattr(response, 'timestamp') or not response.timestamp:
            response.timestamp = int(time.time())
    
    def get_registered_handlers(self) -> Dict[int, Callable]:
        """
        获取当前类注册的处理器
        
        Returns:
            处理器字典
        """
        handlers = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, '_handler_cmd'):
                handlers[attr._handler_cmd] = attr
        return handlers


def get_handler_registry() -> Dict[int, Callable]:
    """获取全局处理器注册表"""
    return HANDLER_REGISTRY.copy()


def register_handler_class(handler_instance: BaseHandler) -> None:
    """
    注册处理器类的所有方法
    
    Args:
        handler_instance: 处理器实例
    """
    for attr_name in dir(handler_instance):
        attr = getattr(handler_instance, attr_name)
        if hasattr(attr, '_handler_cmd'):
            cmd = attr._handler_cmd
            if cmd not in HANDLER_REGISTRY:
                HANDLER_REGISTRY[cmd] = attr
                logger.info(f"注册处理器: cmd={cmd} method={attr_name}")