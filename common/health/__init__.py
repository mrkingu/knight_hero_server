"""
健康检查系统
Health Check System

作者: mrkingu
日期: 2025-06-20
描述: 监控服务健康状态，提供统一的健康检查接口
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HealthChecker(ABC):
    """健康检查器基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.last_check_time = 0
        self.last_status = "unknown"
        self.last_error = None
    
    @abstractmethod
    async def check(self) -> Dict[str, Any]:
        """
        执行健康检查
        
        Returns:
            健康检查结果，包含：
            - status: "healthy", "unhealthy", "warning"
            - message: 状态描述
            - details: 详细信息
            - timestamp: 检查时间戳
        """
        pass
    
    async def safe_check(self) -> Dict[str, Any]:
        """安全的健康检查，捕获异常"""
        try:
            self.last_check_time = time.time()
            result = await self.check()
            
            # 标准化结果格式
            if "status" not in result:
                result["status"] = "healthy"
            if "timestamp" not in result:
                result["timestamp"] = self.last_check_time
            if "checker" not in result:
                result["checker"] = self.name
            
            self.last_status = result["status"]
            self.last_error = None
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.last_error = error_msg
            self.last_status = "error"
            
            logger.error(f"Health check failed for {self.name}: {e}")
            
            return {
                "status": "error",
                "message": f"Health check failed: {error_msg}",
                "checker": self.name,
                "timestamp": time.time(),
                "error": error_msg
            }


class DatabaseHealthChecker(HealthChecker):
    """数据库健康检查器"""
    
    def __init__(self, database_client, timeout: float = 5.0):
        super().__init__("database")
        self.client = database_client
        self.timeout = timeout
    
    async def check(self) -> Dict[str, Any]:
        """检查数据库连接"""
        start_time = time.time()
        
        try:
            # 执行简单的ping操作
            await asyncio.wait_for(
                self.client.admin.command('ping'),
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            
            if response_time > self.timeout * 0.8:
                status = "warning"
                message = f"Database response slow: {response_time:.3f}s"
            else:
                status = "healthy"
                message = f"Database connection OK: {response_time:.3f}s"
            
            return {
                "status": status,
                "message": message,
                "details": {
                    "response_time": response_time,
                    "timeout": self.timeout
                }
            }
            
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "message": f"Database timeout after {self.timeout}s",
                "details": {"timeout": self.timeout}
            }


class RedisHealthChecker(HealthChecker):
    """Redis健康检查器"""
    
    def __init__(self, redis_client, timeout: float = 5.0):
        super().__init__("redis")
        self.client = redis_client
        self.timeout = timeout
    
    async def check(self) -> Dict[str, Any]:
        """检查Redis连接"""
        start_time = time.time()
        
        try:
            # 执行ping操作
            await asyncio.wait_for(
                self.client.ping(),
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            
            # 获取Redis信息
            info = await self.client.info()
            memory_usage = info.get("used_memory_human", "unknown")
            connected_clients = info.get("connected_clients", 0)
            
            if response_time > self.timeout * 0.8:
                status = "warning"
                message = f"Redis response slow: {response_time:.3f}s"
            else:
                status = "healthy"
                message = f"Redis connection OK: {response_time:.3f}s"
            
            return {
                "status": status,
                "message": message,
                "details": {
                    "response_time": response_time,
                    "memory_usage": memory_usage,
                    "connected_clients": connected_clients,
                    "timeout": self.timeout
                }
            }
            
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "message": f"Redis timeout after {self.timeout}s",
                "details": {"timeout": self.timeout}
            }


class ServiceHealthChecker(HealthChecker):
    """服务健康检查器"""
    
    def __init__(self, service_name: str, service_instance):
        super().__init__(f"service_{service_name}")
        self.service_name = service_name
        self.service = service_instance
    
    async def check(self) -> Dict[str, Any]:
        """检查服务状态"""
        if not hasattr(self.service, 'health_check'):
            return {
                "status": "warning",
                "message": f"Service {self.service_name} has no health_check method"
            }
        
        try:
            result = await self.service.health_check()
            
            # 如果服务返回了状态，使用它
            if isinstance(result, dict) and "status" in result:
                return result
            
            # 否则认为是健康的
            return {
                "status": "healthy",
                "message": f"Service {self.service_name} is healthy",
                "details": result if isinstance(result, dict) else {}
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Service {self.service_name} health check failed: {e}",
                "error": str(e)
            }


class MemoryHealthChecker(HealthChecker):
    """内存使用健康检查器"""
    
    def __init__(self, warning_threshold: float = 0.8, critical_threshold: float = 0.9):
        super().__init__("memory")
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def check(self) -> Dict[str, Any]:
        """检查内存使用情况"""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            usage_percent = memory.percent / 100.0
            
            if usage_percent >= self.critical_threshold:
                status = "unhealthy"
                message = f"Critical memory usage: {usage_percent:.1%}"
            elif usage_percent >= self.warning_threshold:
                status = "warning"
                message = f"High memory usage: {usage_percent:.1%}"
            else:
                status = "healthy"
                message = f"Memory usage OK: {usage_percent:.1%}"
            
            return {
                "status": status,
                "message": message,
                "details": {
                    "usage_percent": usage_percent,
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "warning_threshold": self.warning_threshold,
                    "critical_threshold": self.critical_threshold
                }
            }
            
        except ImportError:
            return {
                "status": "warning",
                "message": "psutil not available for memory monitoring"
            }


class DiskHealthChecker(HealthChecker):
    """磁盘空间健康检查器"""
    
    def __init__(self, path: str = "/", warning_threshold: float = 0.8, critical_threshold: float = 0.9):
        super().__init__("disk")
        self.path = path
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def check(self) -> Dict[str, Any]:
        """检查磁盘空间"""
        try:
            import shutil
            
            total, used, free = shutil.disk_usage(self.path)
            usage_percent = used / total
            
            if usage_percent >= self.critical_threshold:
                status = "unhealthy"
                message = f"Critical disk usage: {usage_percent:.1%}"
            elif usage_percent >= self.warning_threshold:
                status = "warning"
                message = f"High disk usage: {usage_percent:.1%}"
            else:
                status = "healthy"
                message = f"Disk usage OK: {usage_percent:.1%}"
            
            return {
                "status": status,
                "message": message,
                "details": {
                    "path": self.path,
                    "usage_percent": usage_percent,
                    "total_gb": total / (1024**3),
                    "used_gb": used / (1024**3),
                    "free_gb": free / (1024**3),
                    "warning_threshold": self.warning_threshold,
                    "critical_threshold": self.critical_threshold
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to check disk usage: {e}",
                "error": str(e)
            }


class HealthCheckService:
    """健康检查服务"""
    
    def __init__(self):
        self.checkers: List[HealthChecker] = []
        self.check_interval = 30  # 默认30秒检查一次
        self.last_results: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def register_checker(self, checker: HealthChecker):
        """注册健康检查器"""
        self.checkers.append(checker)
        logger.info(f"Registered health checker: {checker.name}")
    
    def remove_checker(self, checker_name: str):
        """移除健康检查器"""
        self.checkers = [c for c in self.checkers if c.name != checker_name]
        if checker_name in self.last_results:
            del self.last_results[checker_name]
        logger.info(f"Removed health checker: {checker_name}")
    
    async def check_all(self) -> Dict[str, Any]:
        """执行所有健康检查"""
        results = {}
        overall_status = "healthy"
        unhealthy_count = 0
        warning_count = 0
        
        # 并发执行所有检查
        tasks = []
        checker_names = []
        
        for checker in self.checkers:
            task = asyncio.create_task(checker.safe_check())
            tasks.append(task)
            checker_names.append(checker.name)
        
        if tasks:
            check_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for checker_name, result in zip(checker_names, check_results):
                if isinstance(result, Exception):
                    results[checker_name] = {
                        "status": "error",
                        "message": f"Check failed: {result}",
                        "checker": checker_name,
                        "timestamp": time.time(),
                        "error": str(result)
                    }
                    overall_status = "unhealthy"
                    unhealthy_count += 1
                else:
                    results[checker_name] = result
                    
                    if result["status"] == "unhealthy" or result["status"] == "error":
                        overall_status = "unhealthy"
                        unhealthy_count += 1
                    elif result["status"] == "warning":
                        if overall_status == "healthy":
                            overall_status = "warning"
                        warning_count += 1
        
        # 更新缓存
        self.last_results = results
        
        # 构建汇总结果
        summary = {
            "status": overall_status,
            "timestamp": time.time(),
            "checks": results,
            "summary": {
                "total_checks": len(self.checkers),
                "healthy_checks": len(self.checkers) - unhealthy_count - warning_count,
                "warning_checks": warning_count,
                "unhealthy_checks": unhealthy_count
            }
        }
        
        return summary
    
    async def check_single(self, checker_name: str) -> Optional[Dict[str, Any]]:
        """检查单个检查器"""
        for checker in self.checkers:
            if checker.name == checker_name:
                result = await checker.safe_check()
                self.last_results[checker_name] = result
                return result
        return None
    
    def get_last_results(self) -> Dict[str, Any]:
        """获取最后一次检查结果"""
        if not self.last_results:
            return {
                "status": "unknown",
                "message": "No health checks performed yet",
                "timestamp": time.time(),
                "checks": {}
            }
        
        # 计算整体状态
        overall_status = "healthy"
        for result in self.last_results.values():
            if result["status"] in ("unhealthy", "error"):
                overall_status = "unhealthy"
                break
            elif result["status"] == "warning" and overall_status == "healthy":
                overall_status = "warning"
        
        return {
            "status": overall_status,
            "timestamp": max(r.get("timestamp", 0) for r in self.last_results.values()),
            "checks": self.last_results,
            "summary": {
                "total_checks": len(self.last_results),
                "healthy_checks": sum(1 for r in self.last_results.values() 
                                    if r["status"] == "healthy"),
                "warning_checks": sum(1 for r in self.last_results.values() 
                                    if r["status"] == "warning"),
                "unhealthy_checks": sum(1 for r in self.last_results.values() 
                                      if r["status"] in ("unhealthy", "error"))
            }
        }
    
    async def start_monitoring(self, interval: Optional[int] = None):
        """开始后台监控"""
        if self._running:
            return
        
        if interval:
            self.check_interval = interval
        
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Started health monitoring with {self.check_interval}s interval")
    
    async def stop_monitoring(self):
        """停止后台监控"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped health monitoring")
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self._running:
            try:
                results = await self.check_all()
                
                # 记录关键状态变化
                if results["status"] != "healthy":
                    logger.warning(f"Health check status: {results['status']}")
                    
                    # 记录不健康的检查器
                    for name, result in results["checks"].items():
                        if result["status"] in ("unhealthy", "error"):
                            logger.error(f"Health check failed - {name}: {result['message']}")
                        elif result["status"] == "warning":
                            logger.warning(f"Health check warning - {name}: {result['message']}")
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.check_interval)


# 全局健康检查服务实例
health_service = HealthCheckService()