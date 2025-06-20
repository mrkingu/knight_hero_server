"""
性能优化工具集
Performance Optimization Tools

作者: mrkingu
日期: 2025-06-20
描述: 提供各种性能优化装饰器和工具，包括缓存、批量处理、对象池等
"""
import asyncio
import functools
import time
import weakref
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from concurrent.futures import ThreadPoolExecutor
import threading
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


def async_cached(ttl: int = 60, maxsize: int = 128):
    """
    异步缓存装饰器
    
    Args:
        ttl: 缓存时间(秒)
        maxsize: 最大缓存条目数
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        access_times = {}
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            current_time = time.time()
            
            # 检查缓存
            if cache_key in cache:
                value, expire_time = cache[cache_key]
                if current_time < expire_time:
                    access_times[cache_key] = current_time
                    return value
                else:
                    # 清理过期缓存
                    del cache[cache_key]
                    if cache_key in access_times:
                        del access_times[cache_key]
            
            # 清理超过最大大小的缓存 (LRU)
            if len(cache) >= maxsize:
                # 找到最老的访问记录并删除
                oldest_key = min(access_times.keys(), key=lambda k: access_times[k])
                del cache[oldest_key]
                del access_times[oldest_key]
                    
            # 执行函数
            result = await func(*args, **kwargs)
            
            # 存入缓存
            cache[cache_key] = (result, current_time + ttl)
            access_times[cache_key] = current_time
            
            return result
            
        wrapper._cache = cache
        wrapper._access_times = access_times
        
        def clear_cache():
            """清空缓存"""
            cache.clear()
            access_times.clear()
            
        def get_cache_stats():
            """获取缓存统计"""
            current_time = time.time()
            valid_entries = sum(1 for _, (_, expire_time) in cache.items() 
                              if current_time < expire_time)
            return {
                "total_entries": len(cache),
                "valid_entries": valid_entries,
                "expired_entries": len(cache) - valid_entries,
                "maxsize": maxsize,
                "ttl": ttl
            }
        
        wrapper.clear_cache = clear_cache
        wrapper.get_cache_stats = get_cache_stats
        
        return wrapper
        
    return decorator


def batch_process(batch_size: int = 100, timeout: float = 0.1, max_workers: int = 1):
    """
    批量处理装饰器
    
    Args:
        batch_size: 批量大小
        timeout: 超时时间(秒)
        max_workers: 最大工作线程数
    """
    def decorator(func: Callable) -> Callable:
        queue = asyncio.Queue()
        processing = False
        
        async def processor():
            """批量处理器"""
            nonlocal processing
            processing = True
            
            try:
                while True:
                    batch = []
                    deadline = time.time() + timeout
                    
                    # 收集批量
                    while len(batch) < batch_size and time.time() < deadline:
                        try:
                            remaining = deadline - time.time()
                            if remaining <= 0:
                                break
                                
                            item = await asyncio.wait_for(
                                queue.get(), 
                                timeout=remaining
                            )
                            batch.append(item)
                        except asyncio.TimeoutError:
                            break
                            
                    if batch:
                        # 批量处理
                        try:
                            await func(batch)
                        except Exception as e:
                            logger.error(f"Batch processing error: {e}")
                        
                        # 标记任务完成
                        for _ in batch:
                            queue.task_done()
                    else:
                        # 如果没有任务，休眠一下
                        await asyncio.sleep(0.01)
                        
            finally:
                processing = False
        
        @functools.wraps(func)
        async def wrapper(item):
            nonlocal processing
            
            # 如果处理器没有运行，启动它
            if not processing:
                asyncio.create_task(processor())
            
            await queue.put(item)
            
        return wrapper
        
    return decorator


class ObjectPool(Generic[T]):
    """
    对象池 - 减少对象创建开销
    
    Args:
        factory: 对象工厂函数
        size: 池大小
        max_idle_time: 最大空闲时间(秒)
    """
    
    def __init__(self, factory: Callable[[], T], size: int = 100, max_idle_time: int = 300):
        self.factory = factory
        self.max_size = size
        self.max_idle_time = max_idle_time
        self.pool = asyncio.Queue(maxsize=size)
        self._created = 0
        self._acquired = 0
        self._released = 0
        self._lock = asyncio.Lock()
        
        # 对象创建时间跟踪
        self._object_times = weakref.WeakKeyDictionary()
        
        # 启动清理任务
        asyncio.create_task(self._cleanup_task())
        
    async def acquire(self) -> T:
        """获取对象"""
        self._acquired += 1
        
        try:
            obj = self.pool.get_nowait()
            # 检查对象是否过期
            if obj in self._object_times:
                if time.time() - self._object_times[obj] > self.max_idle_time:
                    # 对象过期，创建新的
                    return self._create_object()
            return obj
        except asyncio.QueueEmpty:
            return self._create_object()
                
    async def release(self, obj: T):
        """释放对象"""
        if obj is None:
            return
            
        self._released += 1
        
        try:
            # 记录释放时间
            self._object_times[obj] = time.time()
            
            # 尝试放回池中
            self.pool.put_nowait(obj)
        except asyncio.QueueFull:
            # 池满了，丢弃对象
            pass
            
    def _create_object(self) -> T:
        """创建新对象"""
        self._created += 1
        obj = self.factory()
        self._object_times[obj] = time.time()
        return obj
        
    async def _cleanup_task(self):
        """清理过期对象的任务"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 清理过期对象
                current_time = time.time()
                expired_objects = []
                
                # 从池中取出所有对象进行检查
                while True:
                    try:
                        obj = self.pool.get_nowait()
                        if obj in self._object_times:
                            if current_time - self._object_times[obj] > self.max_idle_time:
                                expired_objects.append(obj)
                            else:
                                # 对象还有效，放回池中
                                await self.release(obj)
                        else:
                            # 没有时间记录，假设有效
                            await self.release(obj)
                    except asyncio.QueueEmpty:
                        break
                
                logger.debug(f"Cleaned up {len(expired_objects)} expired objects from pool")
                
            except Exception as e:
                logger.error(f"Object pool cleanup error: {e}")
                
    def get_stats(self) -> dict:
        """获取对象池统计信息"""
        return {
            "pool_size": self.pool.qsize(),
            "max_size": self.max_size,
            "created": self._created,
            "acquired": self._acquired,
            "released": self._released,
            "max_idle_time": self.max_idle_time
        }


def rate_limit(calls: int, period: int = 60):
    """
    频率限制装饰器
    
    Args:
        calls: 允许的调用次数
        period: 时间窗口(秒)
    """
    def decorator(func: Callable) -> Callable:
        call_times = []
        lock = threading.Lock()
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_time = time.time()
            
            with lock:
                # 清理过期的调用记录
                call_times[:] = [t for t in call_times if current_time - t < period]
                
                # 检查频率限制
                if len(call_times) >= calls:
                    raise Exception(f"Rate limit exceeded: {calls} calls per {period} seconds")
                
                # 记录当前调用
                call_times.append(current_time)
            
            return await func(*args, **kwargs)
            
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            current_time = time.time()
            
            with lock:
                # 清理过期的调用记录
                call_times[:] = [t for t in call_times if current_time - t < period]
                
                # 检查频率限制
                if len(call_times) >= calls:
                    raise Exception(f"Rate limit exceeded: {calls} calls per {period} seconds")
                
                # 记录当前调用
                call_times.append(current_time)
            
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
        
    return decorator


def circuit_breaker(failure_threshold: int = 5, timeout: int = 60):
    """
    熔断器装饰器
    
    Args:
        failure_threshold: 失败阈值
        timeout: 熔断超时时间(秒)
    """
    def decorator(func: Callable) -> Callable:
        failures = 0
        last_failure_time = 0
        lock = threading.Lock()
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            nonlocal failures, last_failure_time
            
            with lock:
                current_time = time.time()
                
                # 检查熔断状态
                if failures >= failure_threshold:
                    if current_time - last_failure_time < timeout:
                        raise Exception("Circuit breaker is OPEN")
                    else:
                        # 尝试半开状态
                        failures = failure_threshold - 1
            
            try:
                result = await func(*args, **kwargs)
                # 成功时重置失败计数
                with lock:
                    failures = 0
                return result
            except Exception as e:
                # 失败时增加计数
                with lock:
                    failures += 1
                    last_failure_time = time.time()
                raise e
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            nonlocal failures, last_failure_time
            
            with lock:
                current_time = time.time()
                
                # 检查熔断状态
                if failures >= failure_threshold:
                    if current_time - last_failure_time < timeout:
                        raise Exception("Circuit breaker is OPEN")
                    else:
                        # 尝试半开状态
                        failures = failure_threshold - 1
            
            try:
                result = func(*args, **kwargs)
                # 成功时重置失败计数
                with lock:
                    failures = 0
                return result
            except Exception as e:
                # 失败时增加计数
                with lock:
                    failures += 1
                    last_failure_time = time.time()
                raise e
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
        
    return decorator


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.metrics = {}
        self.lock = threading.Lock()
    
    def record(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """记录性能指标"""
        with self.lock:
            if name not in self.metrics:
                self.metrics[name] = {
                    "count": 0,
                    "total": 0,
                    "min": float('inf'),
                    "max": 0,
                    "avg": 0,
                    "tags": tags or {}
                }
            
            metric = self.metrics[name]
            metric["count"] += 1
            metric["total"] += value
            metric["min"] = min(metric["min"], value)
            metric["max"] = max(metric["max"], value)
            metric["avg"] = metric["total"] / metric["count"]
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        with self.lock:
            return self.metrics.copy()
    
    def reset(self):
        """重置所有指标"""
        with self.lock:
            self.metrics.clear()


# 全局性能监控实例
performance_monitor = PerformanceMonitor()


def monitor_performance(name: Optional[str] = None):
    """
    性能监控装饰器
    
    Args:
        name: 指标名称，默认使用函数名
    """
    def decorator(func: Callable) -> Callable:
        metric_name = name or func.__name__
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                elapsed = time.time() - start_time
                performance_monitor.record(metric_name, elapsed)
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.time() - start_time
                performance_monitor.record(metric_name, elapsed)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
        
    return decorator