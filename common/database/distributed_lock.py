"""
分布式锁实现
用于保护关键数据的并发修改
作者: lx
日期: 2025-06-18
"""
import asyncio
import time
import uuid
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)


class DistributedLockError(Exception):
    """分布式锁相关错误"""
    pass


class DeadlockError(DistributedLockError):
    """死锁错误"""
    pass


class LockTimeoutError(DistributedLockError):
    """锁超时错误"""
    pass


class DistributedLock:
    """基于Redis的分布式锁"""
    
    # Lua脚本用于原子释放锁
    RELEASE_SCRIPT = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
    """
    
    # Lua脚本用于原子续期锁
    RENEW_SCRIPT = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
    """
    
    def __init__(
        self, 
        redis_client, 
        lock_key: str,
        timeout: float = 30.0,
        retry_delay: float = 0.1,
        max_retries: int = 10,
        auto_renewal: bool = True
    ):
        """
        初始化分布式锁
        
        Args:
            redis_client: Redis客户端
            lock_key: 锁的键名
            timeout: 锁超时时间(秒)
            retry_delay: 重试间隔时间(秒)
            max_retries: 最大重试次数
            auto_renewal: 是否自动续期
        """
        self.redis_client = redis_client
        self.lock_key = f"lock:{lock_key}"
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.auto_renewal = auto_renewal
        
        # 唯一标识符，用于确保只有锁的持有者才能释放锁
        self.lock_value = str(uuid.uuid4())
        self.acquired = False
        self.renewal_task: Optional[asyncio.Task] = None
        
        # 死锁检测
        self.acquire_start_time: Optional[float] = None
        self.deadlock_detection_timeout = timeout * 3  # 3倍超时时间检测死锁
    
    async def acquire(self) -> bool:
        """
        获取锁
        
        Returns:
            bool: 是否成功获取锁
            
        Raises:
            LockTimeoutError: 获取锁超时
            DeadlockError: 检测到死锁
        """
        self.acquire_start_time = time.time()
        
        for attempt in range(self.max_retries + 1):
            try:
                # 使用SET命令的原子操作获取锁
                result = await self.redis_client.set(
                    self.lock_key,
                    self.lock_value,
                    ex=int(self.timeout),
                    nx=True  # 只在键不存在时设置
                )
                
                if result:
                    self.acquired = True
                    
                    # 启动自动续期任务
                    if self.auto_renewal:
                        self.renewal_task = asyncio.create_task(
                            self._auto_renewal()
                        )
                    
                    logger.debug(f"成功获取锁: {self.lock_key}")
                    return True
                
                # 检查死锁
                current_time = time.time()
                if (current_time - self.acquire_start_time) > self.deadlock_detection_timeout:
                    raise DeadlockError(f"死锁检测: {self.lock_key}")
                
                # 等待重试
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    
            except Exception as e:
                if isinstance(e, (DeadlockError, LockTimeoutError)):
                    raise
                logger.error(f"获取锁时发生错误: {self.lock_key}, {e}")
                raise DistributedLockError(f"获取锁失败: {e}")
        
        # 超时后仍未获取到锁
        total_wait_time = time.time() - self.acquire_start_time
        raise LockTimeoutError(
            f"获取锁超时: {self.lock_key}, 等待时间: {total_wait_time:.2f}s"
        )
    
    async def release(self) -> bool:
        """
        释放锁
        
        Returns:
            bool: 是否成功释放锁
        """
        if not self.acquired:
            return True
        
        try:
            # 停止自动续期任务
            if self.renewal_task and not self.renewal_task.done():
                self.renewal_task.cancel()
                try:
                    await self.renewal_task
                except asyncio.CancelledError:
                    pass
            
            # 使用Lua脚本原子释放锁
            result = await self.redis_client.eval(
                self.RELEASE_SCRIPT,
                1,
                self.lock_key,
                self.lock_value
            )
            
            self.acquired = False
            
            if result == 1:
                logger.debug(f"成功释放锁: {self.lock_key}")
                return True
            else:
                logger.warning(f"锁已被其他进程释放或过期: {self.lock_key}")
                return False
                
        except Exception as e:
            logger.error(f"释放锁时发生错误: {self.lock_key}, {e}")
            return False
    
    async def renew(self, extend_time: Optional[float] = None) -> bool:
        """
        手动续期锁
        
        Args:
            extend_time: 延长时间(秒)，默认使用初始超时时间
            
        Returns:
            bool: 是否成功续期
        """
        if not self.acquired:
            return False
        
        extend_time = extend_time or self.timeout
        
        try:
            result = await self.redis_client.eval(
                self.RENEW_SCRIPT,
                1,
                self.lock_key,
                self.lock_value,
                int(extend_time)
            )
            
            if result == 1:
                logger.debug(f"成功续期锁: {self.lock_key}, 延长: {extend_time}s")
                return True
            else:
                logger.warning(f"续期失败，锁可能已过期: {self.lock_key}")
                self.acquired = False
                return False
                
        except Exception as e:
            logger.error(f"续期锁时发生错误: {self.lock_key}, {e}")
            return False
    
    async def _auto_renewal(self) -> None:
        """自动续期锁的后台任务"""
        renewal_interval = self.timeout / 3  # 每1/3超时时间续期一次
        
        while self.acquired:
            try:
                await asyncio.sleep(renewal_interval)
                
                if self.acquired:
                    success = await self.renew()
                    if not success:
                        logger.error(f"自动续期失败: {self.lock_key}")
                        break
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动续期过程中发生错误: {self.lock_key}, {e}")
                break
    
    async def is_locked(self) -> bool:
        """检查锁是否被持有"""
        try:
            value = await self.redis_client.get(self.lock_key)
            return value is not None
        except Exception:
            return False
    
    async def get_lock_info(self) -> Dict[str, Any]:
        """获取锁的详细信息"""
        try:
            value = await self.redis_client.get(self.lock_key)
            ttl = await self.redis_client.ttl(self.lock_key)
            
            return {
                "lock_key": self.lock_key,
                "is_locked": value is not None,
                "is_owned_by_self": value == self.lock_value if value else False,
                "ttl": ttl,
                "lock_value": value
            }
        except Exception as e:
            return {
                "lock_key": self.lock_key,
                "error": str(e)
            }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.release()


class ReentrantLock:
    """可重入锁实现"""
    
    def __init__(self, redis_client, lock_key: str, **kwargs):
        self.redis_client = redis_client
        self.lock_key = lock_key
        self.kwargs = kwargs
        self.thread_id = f"{asyncio.current_task().get_name()}_{id(asyncio.current_task())}"
        self.reentrant_key = f"reentrant:{lock_key}:{self.thread_id}"
        self.count = 0
        self.base_lock: Optional[DistributedLock] = None
    
    async def acquire(self) -> bool:
        """获取可重入锁"""
        # 检查是否已经持有锁
        current_count = await self.redis_client.get(self.reentrant_key)
        
        if current_count is not None:
            # 已持有锁，增加计数
            self.count = int(current_count) + 1
            await self.redis_client.set(self.reentrant_key, self.count, ex=3600)
            return True
        
        # 首次获取锁
        self.base_lock = DistributedLock(
            self.redis_client,
            self.lock_key,
            **self.kwargs
        )
        
        if await self.base_lock.acquire():
            self.count = 1
            await self.redis_client.set(self.reentrant_key, self.count, ex=3600)
            return True
        
        return False
    
    async def release(self) -> bool:
        """释放可重入锁"""
        if self.count <= 0:
            return True
        
        self.count -= 1
        
        if self.count > 0:
            # 还有重入，只更新计数
            await self.redis_client.set(self.reentrant_key, self.count, ex=3600)
            return True
        else:
            # 完全释放锁
            await self.redis_client.delete(self.reentrant_key)
            if self.base_lock:
                return await self.base_lock.release()
            return True
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


@asynccontextmanager
async def distributed_lock(
    redis_client,
    lock_key: str,
    timeout: float = 30.0,
    **kwargs
):
    """分布式锁的便捷异步上下文管理器"""
    lock = DistributedLock(redis_client, lock_key, timeout=timeout, **kwargs)
    try:
        await lock.acquire()
        yield lock
    finally:
        await lock.release()


@asynccontextmanager  
async def reentrant_lock(
    redis_client,
    lock_key: str,
    **kwargs
):
    """可重入锁的便捷异步上下文管理器"""
    lock = ReentrantLock(redis_client, lock_key, **kwargs)
    try:
        await lock.acquire()
        yield lock
    finally:
        await lock.release()