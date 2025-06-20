"""
统一装饰器工具
作者: lx
日期: 2025-06-20
"""
import asyncio
import time
import logging
from typing import Any, Callable, Optional, Union
from functools import wraps

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Exception, tuple] = Exception
):
    """
    重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间倍数
        exceptions: 需要重试的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise e
                    
                    logging.warning(
                        f"Attempt {attempt} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay} seconds..."
                    )
                    
                    await asyncio.sleep(current_delay)
                    attempt += 1
                    current_delay *= backoff
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise e
                    
                    logging.warning(
                        f"Attempt {attempt} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay} seconds..."
                    )
                    
                    time.sleep(current_delay)
                    attempt += 1
                    current_delay *= backoff
        
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def timeout(seconds: float):
    """
    超时装饰器
    
    Args:
        seconds: 超时时间（秒）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 对于同步函数，我们不能真正实现超时，只能记录开始时间
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            if elapsed > seconds:
                logging.warning(f"Function {func.__name__} took {elapsed:.2f}s (expected < {seconds}s)")
            
            return result
        
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def rate_limit(calls_per_second: float):
    """
    限流装饰器
    
    Args:
        calls_per_second: 每秒允许的调用次数
    """
    min_interval = 1.0 / calls_per_second
    last_called = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            now = time.time()
            func_key = id(func)
            
            if func_key in last_called:
                elapsed = now - last_called[func_key]
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
            
            last_called[func_key] = time.time()
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            now = time.time()
            func_key = id(func)
            
            if func_key in last_called:
                elapsed = now - last_called[func_key]
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
            
            last_called[func_key] = time.time()
            return func(*args, **kwargs)
        
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def cache(ttl: Optional[float] = None):
    """
    缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒），None表示永不过期
    """
    cache_storage = {}
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 创建缓存键
            cache_key = (func.__name__, args, tuple(sorted(kwargs.items())))
            
            # 检查缓存
            if cache_key in cache_storage:
                cached_result, cached_time = cache_storage[cache_key]
                if ttl is None or time.time() - cached_time < ttl:
                    return cached_result
            
            # 执行函数并缓存结果
            result = await func(*args, **kwargs)
            cache_storage[cache_key] = (result, time.time())
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 创建缓存键
            cache_key = (func.__name__, args, tuple(sorted(kwargs.items())))
            
            # 检查缓存
            if cache_key in cache_storage:
                cached_result, cached_time = cache_storage[cache_key]
                if ttl is None or time.time() - cached_time < ttl:
                    return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_storage[cache_key] = (result, time.time())
            return result
        
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def log_execution(logger: Optional[logging.Logger] = None):
    """
    记录执行日志的装饰器
    
    Args:
        logger: 日志记录器
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"Starting execution of {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info(f"Completed {func.__name__} in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"Failed {func.__name__} in {elapsed:.3f}s: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"Starting execution of {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.info(f"Completed {func.__name__} in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"Failed {func.__name__} in {elapsed:.3f}s: {e}")
                raise
        
        # 检查是否是异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

__all__ = ['retry', 'timeout', 'rate_limit', 'cache', 'log_execution']