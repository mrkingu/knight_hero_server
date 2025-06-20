"""
统一的调试工具
Unified Debugging Tools

作者: mrkingu
日期: 2025-06-20
描述: 提供开发时的调试支持，包括函数追踪、性能分析、内存监控等
"""
import asyncio
import functools
import time
import traceback
import threading
import gc
from typing import Any, Callable, Dict, Optional, List
from collections import deque, defaultdict
import logging

# Optional dependencies
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

logger = logging.getLogger(__name__)


class DebugTracer:
    """调试追踪器"""
    
    def __init__(self, max_traces: int = 1000):
        self.max_traces = max_traces
        self._traces: deque = deque(maxlen=max_traces)
        self._call_stack: List[Dict] = []
        self._enabled = True
        self._lock = threading.Lock()
        
    def enable(self):
        """启用追踪"""
        self._enabled = True
        
    def disable(self):
        """禁用追踪"""
        self._enabled = False
        
    def trace(self, include_args: bool = True, include_result: bool = True):
        """
        函数调用追踪装饰器
        
        Args:
            include_args: 是否包含参数
            include_result: 是否包含返回值
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not self._enabled:
                    return await func(*args, **kwargs)
                
                start_time = time.time()
                func_name = f"{func.__module__}.{func.__name__}"
                call_id = id(asyncio.current_task())
                
                # 记录调用开始
                call_info = {
                    "call_id": call_id,
                    "function": func_name,
                    "start_time": start_time,
                    "args": args if include_args else None,
                    "kwargs": kwargs if include_args else None,
                    "thread_id": threading.get_ident(),
                    "stack_depth": len(self._call_stack)
                }
                
                with self._lock:
                    self._call_stack.append(call_info)
                
                print(f"[TRACE] {'  ' * len(self._call_stack)}→ Calling {func_name}")
                if include_args:
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Args: {args}")
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Kwargs: {kwargs}")
                
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    
                    print(f"[TRACE] {'  ' * len(self._call_stack)}← {func_name} completed in {elapsed:.3f}s")
                    if include_result:
                        print(f"[TRACE] {'  ' * len(self._call_stack)}  Result: {result}")
                    
                    # 记录成功调用
                    call_info.update({
                        "end_time": time.time(),
                        "duration": elapsed,
                        "result": result if include_result else None,
                        "success": True
                    })
                    
                    with self._lock:
                        self._traces.append(call_info.copy())
                        self._call_stack.pop()
                    
                    return result
                    
                except Exception as e:
                    elapsed = time.time() - start_time
                    
                    print(f"[TRACE] {'  ' * len(self._call_stack)}✗ {func_name} failed after {elapsed:.3f}s")
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Error: {e}")
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Traceback: {traceback.format_exc()}")
                    
                    # 记录失败调用
                    call_info.update({
                        "end_time": time.time(),
                        "duration": elapsed,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "success": False
                    })
                    
                    with self._lock:
                        self._traces.append(call_info.copy())
                        self._call_stack.pop()
                    
                    raise
                    
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not self._enabled:
                    return func(*args, **kwargs)
                
                start_time = time.time()
                func_name = f"{func.__module__}.{func.__name__}"
                call_id = threading.get_ident()
                
                call_info = {
                    "call_id": call_id,
                    "function": func_name,
                    "start_time": start_time,
                    "args": args if include_args else None,
                    "kwargs": kwargs if include_args else None,
                    "thread_id": threading.get_ident(),
                    "stack_depth": len(self._call_stack)
                }
                
                with self._lock:
                    self._call_stack.append(call_info)
                
                print(f"[TRACE] {'  ' * len(self._call_stack)}→ Calling {func_name}")
                if include_args:
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Args: {args}")
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Kwargs: {kwargs}")
                
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    
                    print(f"[TRACE] {'  ' * len(self._call_stack)}← {func_name} completed in {elapsed:.3f}s")
                    if include_result:
                        print(f"[TRACE] {'  ' * len(self._call_stack)}  Result: {result}")
                    
                    call_info.update({
                        "end_time": time.time(),
                        "duration": elapsed,
                        "result": result if include_result else None,
                        "success": True
                    })
                    
                    with self._lock:
                        self._traces.append(call_info.copy())
                        self._call_stack.pop()
                    
                    return result
                    
                except Exception as e:
                    elapsed = time.time() - start_time
                    
                    print(f"[TRACE] {'  ' * len(self._call_stack)}✗ {func_name} failed after {elapsed:.3f}s")
                    print(f"[TRACE] {'  ' * len(self._call_stack)}  Error: {e}")
                    
                    call_info.update({
                        "end_time": time.time(),
                        "duration": elapsed,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "success": False
                    })
                    
                    with self._lock:
                        self._traces.append(call_info.copy())
                        self._call_stack.pop()
                    
                    raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
                
        return decorator
    
    def get_traces(self, limit: Optional[int] = None) -> List[Dict]:
        """获取追踪记录"""
        with self._lock:
            traces = list(self._traces)
        
        if limit:
            traces = traces[-limit:]
            
        return traces
    
    def clear_traces(self):
        """清空追踪记录"""
        with self._lock:
            self._traces.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取追踪统计"""
        with self._lock:
            traces = list(self._traces)
        
        stats = {
            "total_calls": len(traces),
            "successful_calls": sum(1 for t in traces if t.get("success", False)),
            "failed_calls": sum(1 for t in traces if not t.get("success", True)),
            "avg_duration": 0,
            "max_duration": 0,
            "min_duration": float('inf'),
            "function_stats": defaultdict(lambda: {"count": 0, "total_time": 0, "errors": 0})
        }
        
        if traces:
            durations = [t.get("duration", 0) for t in traces if t.get("duration")]
            if durations:
                stats["avg_duration"] = sum(durations) / len(durations)
                stats["max_duration"] = max(durations)
                stats["min_duration"] = min(durations)
            
            # 函数统计
            for trace in traces:
                func_name = trace.get("function", "unknown")
                func_stats = stats["function_stats"][func_name]
                func_stats["count"] += 1
                if trace.get("duration"):
                    func_stats["total_time"] += trace["duration"]
                if not trace.get("success", True):
                    func_stats["errors"] += 1
        
        return dict(stats)


class MemoryProfiler:
    """内存分析器"""
    
    def __init__(self):
        self._snapshots: List[Dict] = []
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
    def take_snapshot(self) -> Dict[str, Any]:
        """获取内存快照"""
        if not HAS_PSUTIL:
            return {
                "timestamp": time.time(),
                "error": "psutil not available",
                "gc_stats": {
                    "objects": len(gc.get_objects()),
                    "generation_0": len(gc.get_objects(0)),
                    "generation_1": len(gc.get_objects(1)), 
                    "generation_2": len(gc.get_objects(2)),
                    "collections": gc.get_stats()
                }
            }
            
        process = psutil.Process()
        memory_info = process.memory_info()
        
        snapshot = {
            "timestamp": time.time(),
            "rss": memory_info.rss,  # 物理内存
            "vms": memory_info.vms,  # 虚拟内存
            "percent": process.memory_percent(),
            "gc_stats": {
                "objects": len(gc.get_objects()),
                "generation_0": len(gc.get_objects(0)),
                "generation_1": len(gc.get_objects(1)), 
                "generation_2": len(gc.get_objects(2)),
                "collections": gc.get_stats()
            }
        }
        
        self._snapshots.append(snapshot)
        return snapshot
    
    async def start_monitoring(self, interval: float = 10.0):
        """开始内存监控"""
        if self._monitoring:
            return
            
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))
        
    async def stop_monitoring(self):
        """停止内存监控"""
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitor_loop(self, interval: float):
        """监控循环"""
        while self._monitoring:
            try:
                snapshot = self.take_snapshot()
                
                # 检查内存泄漏
                if len(self._snapshots) > 1:
                    prev = self._snapshots[-2]
                    current = self._snapshots[-1]
                    
                    rss_growth = current["rss"] - prev["rss"]
                    if rss_growth > 50 * 1024 * 1024:  # 50MB增长
                        logger.warning(f"Memory growth detected: {rss_growth / 1024 / 1024:.1f}MB")
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                await asyncio.sleep(interval)
    
    def get_snapshots(self, limit: Optional[int] = None) -> List[Dict]:
        """获取内存快照"""
        if limit:
            return self._snapshots[-limit:]
        return self._snapshots.copy()
    
    def analyze_growth(self) -> Dict[str, Any]:
        """分析内存增长"""
        if len(self._snapshots) < 2:
            return {"error": "Need at least 2 snapshots"}
        
        first = self._snapshots[0]
        last = self._snapshots[-1]
        
        time_span = last["timestamp"] - first["timestamp"]
        rss_growth = last["rss"] - first["rss"]
        vms_growth = last["vms"] - first["vms"]
        
        return {
            "time_span_seconds": time_span,
            "rss_growth_bytes": rss_growth,
            "rss_growth_mb": rss_growth / 1024 / 1024,
            "vms_growth_bytes": vms_growth,
            "vms_growth_mb": vms_growth / 1024 / 1024,
            "growth_rate_mb_per_hour": (rss_growth / 1024 / 1024) / (time_span / 3600) if time_span > 0 else 0,
            "gc_objects_growth": last["gc_stats"]["objects"] - first["gc_stats"]["objects"]
        }


class PerformanceProfiler:
    """性能分析器"""
    
    def __init__(self):
        self._profiles: Dict[str, List[Dict]] = defaultdict(list)
        self._active_profiles: Dict[str, Dict] = {}
        
    def profile(self, name: Optional[str] = None, detailed: bool = False):
        """
        性能分析装饰器
        
        Args:
            name: 分析器名称
            detailed: 是否记录详细信息
        """
        def decorator(func: Callable) -> Callable:
            profile_name = name or f"{func.__module__}.{func.__name__}"
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                start_cpu = time.process_time()
                
                # 记录内存使用
                start_memory = 0
                if HAS_PSUTIL:
                    process = psutil.Process()
                    start_memory = process.memory_info().rss
                
                try:
                    result = await func(*args, **kwargs)
                    
                    end_time = time.time()
                    end_cpu = time.process_time()
                    end_memory = start_memory
                    if HAS_PSUTIL:
                        end_memory = process.memory_info().rss
                    
                    profile_data = {
                        "timestamp": start_time,
                        "wall_time": end_time - start_time,
                        "cpu_time": end_cpu - start_cpu,
                        "memory_delta": end_memory - start_memory,
                        "success": True
                    }
                    
                    if detailed:
                        profile_data.update({
                            "args_count": len(args),
                            "kwargs_count": len(kwargs),
                            "result_type": type(result).__name__,
                            "gc_before": len(gc.get_objects()),
                            "gc_after": len(gc.get_objects())
                        })
                    
                    self._profiles[profile_name].append(profile_data)
                    return result
                    
                except Exception as e:
                    end_time = time.time()
                    end_cpu = time.process_time()
                    end_memory = process.memory_info().rss
                    
                    profile_data = {
                        "timestamp": start_time,
                        "wall_time": end_time - start_time,
                        "cpu_time": end_cpu - start_cpu,
                        "memory_delta": end_memory - start_memory,
                        "success": False,
                        "error": str(e)
                    }
                    
                    self._profiles[profile_name].append(profile_data)
                    raise
                    
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                start_cpu = time.process_time()
                start_memory = 0
                if HAS_PSUTIL:
                    process = psutil.Process()
                    start_memory = process.memory_info().rss
                
                try:
                    result = func(*args, **kwargs)
                    
                    end_time = time.time()
                    end_cpu = time.process_time()
                    end_memory = start_memory
                    if HAS_PSUTIL:
                        end_memory = process.memory_info().rss
                    
                    profile_data = {
                        "timestamp": start_time,
                        "wall_time": end_time - start_time,
                        "cpu_time": end_cpu - start_cpu,
                        "memory_delta": end_memory - start_memory,
                        "success": True
                    }
                    
                    self._profiles[profile_name].append(profile_data)
                    return result
                    
                except Exception as e:
                    end_time = time.time()
                    end_cpu = time.process_time()
                    end_memory = process.memory_info().rss
                    
                    profile_data = {
                        "timestamp": start_time,
                        "wall_time": end_time - start_time,
                        "cpu_time": end_cpu - start_cpu,
                        "memory_delta": end_memory - start_memory,
                        "success": False,
                        "error": str(e)
                    }
                    
                    self._profiles[profile_name].append(profile_data)
                    raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
                
        return decorator
    
    def get_profile(self, name: str) -> List[Dict]:
        """获取特定函数的性能分析数据"""
        return self._profiles.get(name, [])
    
    def get_summary(self, name: str) -> Dict[str, Any]:
        """获取性能分析摘要"""
        profiles = self._profiles.get(name, [])
        if not profiles:
            return {"error": "No profile data found"}
        
        wall_times = [p["wall_time"] for p in profiles]
        cpu_times = [p["cpu_time"] for p in profiles]
        memory_deltas = [p["memory_delta"] for p in profiles]
        
        return {
            "call_count": len(profiles),
            "success_rate": sum(1 for p in profiles if p["success"]) / len(profiles),
            "wall_time": {
                "min": min(wall_times),
                "max": max(wall_times),
                "avg": sum(wall_times) / len(wall_times),
                "total": sum(wall_times)
            },
            "cpu_time": {
                "min": min(cpu_times),
                "max": max(cpu_times),
                "avg": sum(cpu_times) / len(cpu_times),
                "total": sum(cpu_times)
            },
            "memory": {
                "min_delta": min(memory_deltas),
                "max_delta": max(memory_deltas),
                "avg_delta": sum(memory_deltas) / len(memory_deltas),
                "total_delta": sum(memory_deltas)
            }
        }
    
    def clear_profiles(self, name: Optional[str] = None):
        """清空性能分析数据"""
        if name:
            self._profiles.pop(name, None)
        else:
            self._profiles.clear()


# 全局实例
debug_tracer = DebugTracer()
memory_profiler = MemoryProfiler()
performance_profiler = PerformanceProfiler()

# 便捷装饰器
trace = debug_tracer.trace
profile = performance_profiler.profile