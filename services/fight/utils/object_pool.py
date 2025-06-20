"""
战斗对象池
Battle Object Pool

作者: lx
日期: 2025-06-18
描述: 专用于战斗服务的高性能对象池，支持自动扩容和对象重置
"""
from typing import Type, TypeVar, Generic, Optional, List, Dict, Any, Callable
from threading import Lock, RLock
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import weakref
import gc

T = TypeVar('T')


class ObjectPool(Generic[T]):
    """战斗对象池
    
    特性:
    - 自动扩容和收缩
    - 对象重置功能
    - 线程安全
    - 性能统计
    - 内存管理
    """
    
    def __init__(
        self, 
        object_type: Type[T], 
        size: int = 100,
        max_size: Optional[int] = None,
        auto_cleanup: bool = True,
        reset_func: Optional[Callable[[T], None]] = None
    ):
        """初始化对象池
        
        Args:
            object_type: 对象类型
            size: 初始大小
            max_size: 最大大小，None表示无限制
            auto_cleanup: 是否自动清理
            reset_func: 自定义重置函数
        """
        self.object_type = object_type
        self.initial_size = size
        self.max_size = max_size or size * 10
        self.auto_cleanup = auto_cleanup
        self.reset_func = reset_func
        
        # 对象池存储
        self._pool: List[T] = []
        self._lock = RLock()
        
        # 统计信息
        self._stats = {
            "created": 0,
            "reused": 0,
            "reset_count": 0,
            "peak_size": 0,
            "cleanup_count": 0,
            "total_get_time": 0.0,
            "total_put_time": 0.0,
            "get_count": 0,
            "put_count": 0
        }
        
        # 弱引用追踪使用中的对象
        self._active_objects: weakref.WeakSet[T] = weakref.WeakSet()
        
        # 预分配初始对象
        self._prealloc_objects()
        
    def _prealloc_objects(self) -> None:
        """预分配初始对象"""
        with self._lock:
            for _ in range(self.initial_size):
                try:
                    obj = self.object_type()
                    self._pool.append(obj)
                    self._stats["created"] += 1
                except Exception:
                    # 如果创建失败，跳过
                    break
                    
    def get(self) -> T:
        """获取对象
        
        Returns:
            T: 池中的对象或新创建的对象
        """
        start_time = time.perf_counter()
        
        with self._lock:
            try:
                if self._pool:
                    obj = self._pool.pop()
                    self._stats["reused"] += 1
                else:
                    obj = self.object_type()
                    self._stats["created"] += 1
                
                # 添加到活跃对象集合
                self._active_objects.add(obj)
                
                # 更新统计
                self._stats["get_count"] += 1
                self._stats["total_get_time"] += time.perf_counter() - start_time
                
                return obj
                
            except Exception as e:
                # 创建失败时的fallback
                obj = self.object_type()
                self._stats["created"] += 1
                return obj
                
    def put(self, obj: T) -> bool:
        """归还对象
        
        Args:
            obj: 要归还的对象
            
        Returns:
            bool: 是否成功归还
        """
        if not isinstance(obj, self.object_type):
            return False
            
        start_time = time.perf_counter()
        
        with self._lock:
            # 检查池大小限制
            if len(self._pool) >= self.max_size:
                return False
                
            # 重置对象状态
            if self._reset_object(obj):
                self._pool.append(obj)
                self._stats["put_count"] += 1
                self._stats["total_put_time"] += time.perf_counter() - start_time
                self._stats["peak_size"] = max(self._stats["peak_size"], len(self._pool))
                return True
                
        return False
        
    def _reset_object(self, obj: T) -> bool:
        """重置对象状态
        
        Args:
            obj: 要重置的对象
            
        Returns:
            bool: 是否重置成功
        """
        try:
            if self.reset_func:
                self.reset_func(obj)
            elif hasattr(obj, 'reset'):
                obj.reset()
            elif hasattr(obj, 'clear'):
                obj.clear()
            elif hasattr(obj, '__dict__'):
                # 清空实例属性，但保留类属性
                obj.__dict__.clear()
                # 如果有__init__方法，重新初始化
                if hasattr(obj, '__init__'):
                    # 获取初始化参数
                    import inspect
                    sig = inspect.signature(obj.__init__)
                    params = list(sig.parameters.keys())[1:]  # 排除self
                    
                    # 尝试用默认值重新初始化
                    init_args = {}
                    for param_name in params:
                        param = sig.parameters[param_name]
                        if param.default != inspect.Parameter.empty:
                            init_args[param_name] = param.default
                        elif param.annotation:
                            # 根据类型提供默认值
                            if param.annotation == int:
                                init_args[param_name] = 0
                            elif param.annotation == str:
                                init_args[param_name] = ""
                            elif param.annotation == float:
                                init_args[param_name] = 0.0
                            elif param.annotation == bool:
                                init_args[param_name] = False
                            elif hasattr(param.annotation, '__origin__') and param.annotation.__origin__ is list:
                                init_args[param_name] = []
                            elif hasattr(param.annotation, '__origin__') and param.annotation.__origin__ is dict:
                                init_args[param_name] = {}
                    
                    try:
                        obj.__init__(**init_args)
                    except:
                        # 如果重新初始化失败，跳过这个对象
                        return False
                    
            self._stats["reset_count"] += 1
            return True
            
        except Exception:
            # 重置失败时不归还到池中
            return False
            
    def cleanup(self) -> int:
        """清理池中的对象
        
        Returns:
            int: 清理的对象数量
        """
        with self._lock:
            old_size = len(self._pool)
            # 只保留初始大小的对象
            target_size = min(self.initial_size, len(self._pool))
            self._pool = self._pool[:target_size]
            
            cleaned = old_size - len(self._pool)
            self._stats["cleanup_count"] += cleaned
            
            # 强制垃圾回收
            if cleaned > 0:
                gc.collect()
                
            return cleaned
            
    def get_stats(self) -> Dict[str, Any]:
        """获取池统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            get_count = max(self._stats["get_count"], 1)
            put_count = max(self._stats["put_count"], 1)
            
            return {
                "current_size": len(self._pool),
                "initial_size": self.initial_size,
                "max_size": self.max_size,
                "peak_size": self._stats["peak_size"],
                "objects_created": self._stats["created"],
                "objects_reused": self._stats["reused"],
                "reset_count": self._stats["reset_count"],
                "cleanup_count": self._stats["cleanup_count"],
                "active_objects": len(self._active_objects),
                "reuse_rate": self._stats["reused"] / (self._stats["created"] + self._stats["reused"]) * 100,
                "avg_get_time_ms": self._stats["total_get_time"] / get_count * 1000,
                "avg_put_time_ms": self._stats["total_put_time"] / put_count * 1000,
                "get_count": self._stats["get_count"],
                "put_count": self._stats["put_count"]
            }
            
    def resize(self, new_size: int) -> None:
        """调整池大小
        
        Args:
            new_size: 新的目标大小
        """
        with self._lock:
            current_size = len(self._pool)
            
            if new_size > current_size:
                # 扩容：添加新对象
                for _ in range(new_size - current_size):
                    try:
                        obj = self.object_type()
                        self._pool.append(obj)
                        self._stats["created"] += 1
                    except Exception:
                        break
                        
            elif new_size < current_size:
                # 缩容：移除多余对象
                self._pool = self._pool[:new_size]
                
            self.initial_size = new_size


class AsyncObjectPool(ObjectPool[T]):
    """异步对象池
    
    支持异步获取和归还对象，适用于异步环境
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._async_lock = asyncio.Lock()
        
    async def get_async(self) -> T:
        """异步获取对象
        
        Returns:
            T: 池中的对象或新创建的对象
        """
        async with self._async_lock:
            return self.get()
            
    async def put_async(self, obj: T) -> bool:
        """异步归还对象
        
        Args:
            obj: 要归还的对象
            
        Returns:
            bool: 是否成功归还
        """
        async with self._async_lock:
            return self.put(obj)
            
    async def cleanup_async(self) -> int:
        """异步清理池
        
        Returns:
            int: 清理的对象数量
        """
        async with self._async_lock:
            return self.cleanup()


class PoolManager:
    """对象池管理器
    
    管理多个对象池，提供统一的接口和监控
    """
    
    def __init__(self):
        self._pools: Dict[str, ObjectPool] = {}
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pool_mgr")
        
    def create_pool(
        self, 
        name: str, 
        object_type: Type[T], 
        **kwargs
    ) -> ObjectPool[T]:
        """创建对象池
        
        Args:
            name: 池名称
            object_type: 对象类型
            **kwargs: 池参数
            
        Returns:
            ObjectPool[T]: 创建的对象池
        """
        with self._lock:
            if name in self._pools:
                raise ValueError(f"Pool '{name}' already exists")
                
            pool = ObjectPool(object_type, **kwargs)
            self._pools[name] = pool
            return pool
            
    def get_pool(self, name: str) -> Optional[ObjectPool]:
        """获取对象池
        
        Args:
            name: 池名称
            
        Returns:
            Optional[ObjectPool]: 对象池，如果不存在返回None
        """
        with self._lock:
            return self._pools.get(name)
            
    def remove_pool(self, name: str) -> bool:
        """移除对象池
        
        Args:
            name: 池名称
            
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            return self._pools.pop(name, None) is not None
            
    def cleanup_all(self) -> Dict[str, int]:
        """清理所有池
        
        Returns:
            Dict[str, int]: 各池清理的对象数量
        """
        results = {}
        with self._lock:
            for name, pool in self._pools.items():
                results[name] = pool.cleanup()
        return results
        
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有池的统计信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 各池的统计信息
        """
        stats = {}
        with self._lock:
            for name, pool in self._pools.items():
                stats[name] = pool.get_stats()
        return stats
        
    def auto_manage(self, interval: float = 60.0) -> None:
        """启动自动管理
        
        Args:
            interval: 管理间隔（秒）
        """
        def _auto_manage():
            """自动管理任务"""
            try:
                # 定期清理空闲对象
                self.cleanup_all()
                # 强制垃圾回收
                gc.collect()
            except Exception:
                pass
                
        # 在后台线程中定期执行
        self._executor.submit(_auto_manage)
        
    def shutdown(self) -> None:
        """关闭管理器"""
        self._executor.shutdown(wait=True)


# 全局池管理器实例
_pool_manager = PoolManager()


def get_pool_manager() -> PoolManager:
    """获取全局池管理器
    
    Returns:
        PoolManager: 池管理器实例
    """
    return _pool_manager


def create_battle_pool(name: str, object_type: Type[T], **kwargs) -> ObjectPool[T]:
    """创建战斗对象池的便捷函数
    
    Args:
        name: 池名称
        object_type: 对象类型
        **kwargs: 池参数
        
    Returns:
        ObjectPool[T]: 创建的对象池
    """
    return _pool_manager.create_pool(name, object_type, **kwargs)


def get_battle_pool(name: str) -> Optional[ObjectPool]:
    """获取战斗对象池的便捷函数
    
    Args:
        name: 池名称
        
    Returns:
        Optional[ObjectPool]: 对象池
    """
    return _pool_manager.get_pool(name)