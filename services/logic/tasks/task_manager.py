"""
任务管理器
Task Manager

作者: lx
日期: 2025-06-20
描述: 基于Redis的延迟队列、Cron定时任务、分布式锁、任务持久化
"""

import asyncio
import json
import time
import uuid
import logging
from typing import Dict, Any, Callable, Optional, List
from datetime import datetime, timedelta
from functools import wraps
from contextlib import asynccontextmanager
import croniter

from common.database.core import RedisClient

logger = logging.getLogger(__name__)


def scheduled_task(cron: str, description: str = ""):
    """
    定时任务装饰器
    
    Args:
        cron: Cron表达式
        description: 任务描述
        
    Usage:
        @scheduled_task(cron="0 0 * * *", description="每日重置")
        async def daily_reset(self):
            pass
    """
    def decorator(func: Callable) -> Callable:
        func._is_scheduled_task = True
        func._cron_expression = cron
        func._task_description = description
        return func
    return decorator


@asynccontextmanager
async def distributed_lock(
    key: str, 
    timeout: int = 30, 
    retry_interval: float = 0.1,
    redis_client=None
):
    """
    分布式锁上下文管理器
    
    Args:
        key: 锁的键
        timeout: 锁超时时间(秒)
        retry_interval: 重试间隔(秒)
        redis_client: Redis客户端
        
    Usage:
        async with distributed_lock("daily_reset"):
            # 执行需要加锁的操作
            pass
    """
    if redis_client is None:
        redis_config = {'host': 'localhost', 'port': 6379, 'db': 0}
        redis_client = RedisClient(redis_config)
    
    lock_key = f"lock:{key}"
    lock_value = str(uuid.uuid4())
    acquired = False
    
    try:
        # 尝试获取锁
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 使用 SET NX EX 原子操作获取锁
            acquired = await redis_client.client.set(
                lock_key, lock_value, nx=True, ex=timeout
            )
            if acquired:
                logger.debug(f"获取分布式锁成功: {key}")
                break
            await asyncio.sleep(retry_interval)
        
        if not acquired:
            raise TimeoutError(f"获取分布式锁超时: {key}")
        
        yield
        
    finally:
        if acquired:
            # 使用Lua脚本安全释放锁
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            try:
                await redis_client.client.eval(lua_script, 1, lock_key, lock_value)
                logger.debug(f"释放分布式锁: {key}")
            except Exception as e:
                logger.error(f"释放分布式锁失败 {key}: {e}")


class TaskManager:
    """任务管理器"""
    
    def __init__(self, redis_client=None):
        """
        初始化任务管理器
        
        Args:
            redis_client: Redis客户端
        """
        self.redis = redis_client or RedisClient({'host': 'localhost', 'port': 6379, 'db': 0})
        self.running = False
        self.scheduled_tasks: Dict[str, Dict[str, Any]] = {}
        self.delayed_queue_key = "delayed_tasks"
        self.task_workers: List[asyncio.Task] = []
        
    async def start(self):
        """启动任务管理器"""
        if self.running:
            return
            
        self.running = True
        logger.info("启动任务管理器")
        
        # 启动延迟队列处理器
        worker = asyncio.create_task(self._delayed_queue_worker())
        self.task_workers.append(worker)
        
        # 启动定时任务调度器
        scheduler = asyncio.create_task(self._task_scheduler())
        self.task_workers.append(scheduler)
    
    async def stop(self):
        """停止任务管理器"""
        if not self.running:
            return
            
        self.running = False
        logger.info("停止任务管理器")
        
        # 取消所有工作任务
        for worker in self.task_workers:
            worker.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self.task_workers, return_exceptions=True)
        self.task_workers.clear()
    
    def register_scheduled_task(self, task_instance: Any):
        """
        注册定时任务实例
        
        Args:
            task_instance: 任务实例对象
        """
        for attr_name in dir(task_instance):
            attr = getattr(task_instance, attr_name)
            if hasattr(attr, '_is_scheduled_task'):
                cron_expr = attr._cron_expression
                description = attr._task_description
                
                task_info = {
                    "func": attr,
                    "cron": cron_expr,
                    "description": description,
                    "next_run": self._get_next_run_time(cron_expr),
                    "instance": task_instance
                }
                
                self.scheduled_tasks[f"{task_instance.__class__.__name__}.{attr_name}"] = task_info
                logger.info(f"注册定时任务: {attr_name} ({description}) - {cron_expr}")
    
    def _get_next_run_time(self, cron_expr: str) -> datetime:
        """计算下次执行时间"""
        try:
            cron = croniter.croniter(cron_expr, datetime.now())
            return cron.get_next(datetime)
        except Exception as e:
            logger.error(f"解析Cron表达式失败 {cron_expr}: {e}")
            # 默认1小时后执行
            return datetime.now() + timedelta(hours=1)
    
    async def _task_scheduler(self):
        """定时任务调度器"""
        while self.running:
            try:
                current_time = datetime.now()
                
                for task_name, task_info in self.scheduled_tasks.items():
                    if current_time >= task_info["next_run"]:
                        # 使用分布式锁避免重复执行
                        lock_key = f"scheduled_task:{task_name}"
                        
                        try:
                            async with distributed_lock(lock_key, timeout=5):
                                logger.info(f"执行定时任务: {task_name}")
                                await task_info["func"]()
                                
                                # 更新下次执行时间
                                task_info["next_run"] = self._get_next_run_time(
                                    task_info["cron"]
                                )
                                
                        except TimeoutError:
                            logger.warning(f"定时任务 {task_name} 已在其他节点执行")
                        except Exception as e:
                            logger.error(f"执行定时任务失败 {task_name}: {e}")
                
                # 每30秒检查一次
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"任务调度器异常: {e}")
                await asyncio.sleep(30)
    
    async def add_delayed_task(
        self, 
        task_data: Dict[str, Any], 
        delay_seconds: int,
        task_id: Optional[str] = None
    ) -> str:
        """
        添加延迟任务
        
        Args:
            task_data: 任务数据
            delay_seconds: 延迟秒数
            task_id: 任务ID，不提供则自动生成
            
        Returns:
            任务ID
        """
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        execute_time = time.time() + delay_seconds
        
        task_payload = {
            "id": task_id,
            "data": task_data,
            "created_at": time.time(),
            "execute_at": execute_time
        }
        
        # 添加到Redis有序集合
        await self.redis.client.zadd(
            self.delayed_queue_key,
            {json.dumps(task_payload): execute_time}
        )
        
        logger.info(f"添加延迟任务: {task_id} 延迟{delay_seconds}秒")
        return task_id
    
    async def cancel_delayed_task(self, task_id: str) -> bool:
        """
        取消延迟任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        # 获取所有任务
        tasks = await self.redis.client.zrange(self.delayed_queue_key, 0, -1)
        
        for task_json in tasks:
            try:
                task_data = json.loads(task_json)
                if task_data["id"] == task_id:
                    # 删除任务
                    removed = await self.redis.client.zrem(
                        self.delayed_queue_key, task_json
                    )
                    if removed:
                        logger.info(f"取消延迟任务: {task_id}")
                        return True
            except (json.JSONDecodeError, KeyError):
                continue
        
        return False
    
    async def _delayed_queue_worker(self):
        """延迟队列处理器"""
        while self.running:
            try:
                current_time = time.time()
                
                # 获取到期的任务
                tasks = await self.redis.client.zrangebyscore(
                    self.delayed_queue_key, 
                    0, 
                    current_time, 
                    withscores=True
                )
                
                for task_json, score in tasks:
                    try:
                        task_data = json.loads(task_json)
                        task_id = task_data["id"]
                        
                        # 使用分布式锁确保任务只被执行一次
                        lock_key = f"delayed_task:{task_id}"
                        
                        try:
                            async with distributed_lock(lock_key, timeout=1):
                                # 再次检查任务是否还在队列中
                                exists = await self.redis.client.zrem(
                                    self.delayed_queue_key, task_json
                                )
                                
                                if exists:
                                    await self._execute_delayed_task(task_data)
                                    
                        except TimeoutError:
                            # 任务已被其他节点处理
                            continue
                            
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"解析延迟任务失败: {e}")
                        # 删除无效任务
                        await self.redis.client.zrem(self.delayed_queue_key, task_json)
                
                # 每秒检查一次
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"延迟队列处理器异常: {e}")
                await asyncio.sleep(5)
    
    async def _execute_delayed_task(self, task_data: Dict[str, Any]):
        """
        执行延迟任务
        
        Args:
            task_data: 任务数据
        """
        try:
            task_id = task_data["id"]
            data = task_data["data"]
            
            logger.info(f"执行延迟任务: {task_id}")
            
            # 根据任务类型执行不同的处理逻辑
            task_type = data.get("type")
            
            if task_type == "energy_recovery":
                await self._handle_energy_recovery(data)
            elif task_type == "daily_reset":
                await self._handle_daily_reset(data)
            elif task_type == "custom":
                await self._handle_custom_task(data)
            else:
                logger.warning(f"未知的延迟任务类型: {task_type}")
            
        except Exception as e:
            logger.error(f"执行延迟任务失败: {e}")
    
    async def _handle_energy_recovery(self, data: Dict[str, Any]):
        """处理体力恢复任务"""
        player_id = data.get("player_id")
        if player_id:
            # 这里可以调用玩家服务恢复体力
            logger.info(f"恢复玩家体力: {player_id}")
    
    async def _handle_daily_reset(self, data: Dict[str, Any]):
        """处理每日重置任务"""
        logger.info("执行每日重置任务")
        # 实现每日重置逻辑
    
    async def _handle_custom_task(self, data: Dict[str, Any]):
        """处理自定义任务"""
        callback = data.get("callback")
        params = data.get("params", {})
        
        if callback:
            logger.info(f"执行自定义任务: {callback}")
            # 这里可以根据callback动态调用相应的处理函数
    
    async def get_task_stats(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计信息
        """
        # 获取延迟任务数量
        delayed_count = await self.redis.client.zcard(self.delayed_queue_key)
        
        # 统计定时任务
        scheduled_count = len(self.scheduled_tasks)
        
        # 下次执行的定时任务
        next_scheduled = None
        if self.scheduled_tasks:
            next_task = min(
                self.scheduled_tasks.values(),
                key=lambda x: x["next_run"]
            )
            next_scheduled = {
                "name": next_task.get("description", "Unknown"),
                "next_run": next_task["next_run"].isoformat()
            }
        
        return {
            "running": self.running,
            "delayed_tasks": delayed_count,
            "scheduled_tasks": scheduled_count,
            "next_scheduled": next_scheduled
        }