#!/usr/bin/env python3
"""
健康检查模块
Health Check Module

作者: lx
日期: 2025-06-20
描述: 提供HTTP、gRPC、Redis、MongoDB的健康检查功能
"""

import asyncio
import aiohttp
import redis.asyncio as redis
import motor.motor_asyncio
import grpc
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    service: str
    status: HealthStatus
    response_time: float
    details: Dict[str, Any]
    timestamp: float


class HttpHealthChecker:
    """HTTP健康检查器"""
    
    def __init__(self, timeout: float = 5.0):
        """
        初始化HTTP健康检查器
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        
    async def check(self, url: str, expected_status: int = 200) -> HealthCheckResult:
        """
        检查HTTP服务健康状态
        
        Args:
            url: 健康检查URL
            expected_status: 期望的HTTP状态码
            
        Returns:
            健康检查结果
        """
        start_time = time.time()
        service_name = f"http://{url}"
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.get(url) as response:
                    response_time = time.time() - start_time
                    
                    if response.status == expected_status:
                        return HealthCheckResult(
                            service=service_name,
                            status=HealthStatus.HEALTHY,
                            response_time=response_time,
                            details={
                                "status_code": response.status,
                                "content_type": response.headers.get("content-type"),
                                "response_size": len(await response.text())
                            },
                            timestamp=time.time()
                        )
                    else:
                        return HealthCheckResult(
                            service=service_name,
                            status=HealthStatus.UNHEALTHY,
                            response_time=response_time,
                            details={
                                "status_code": response.status,
                                "expected_status": expected_status,
                                "error": f"状态码不匹配: {response.status} != {expected_status}"
                            },
                            timestamp=time.time()
                        )
                        
        except asyncio.TimeoutError:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=self.timeout,
                details={"error": "请求超时"},
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=time.time() - start_time,
                details={"error": str(e)},
                timestamp=time.time()
            )


class GrpcHealthChecker:
    """gRPC健康检查器"""
    
    def __init__(self, timeout: float = 5.0):
        """
        初始化gRPC健康检查器
        
        Args:
            timeout: 请求超时时间（秒）
        """
        self.timeout = timeout
        
    async def check(self, address: str, service_name: str = "") -> HealthCheckResult:
        """
        检查gRPC服务健康状态
        
        Args:
            address: gRPC服务地址
            service_name: 服务名称（可选）
            
        Returns:
            健康检查结果
        """
        start_time = time.time()
        service_id = f"grpc://{address}/{service_name}" if service_name else f"grpc://{address}"
        
        try:
            # 创建gRPC通道
            channel = grpc.aio.insecure_channel(address)
            
            # 使用简单的gRPC连接测试代替health checking protocol
            # 创建gRPC通道并测试连接
            try:
                channel = grpc.aio.insecure_channel(address)
                # 简单的连接测试
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=self.timeout
                )
                
                response_time = time.time() - start_time
                await channel.close()
                
                return HealthCheckResult(
                    service=service_id,
                    status=HealthStatus.HEALTHY,
                    response_time=response_time,
                    details={
                        "grpc_status": "CONNECTED",
                        "service_name": service_name
                    },
                    timestamp=time.time()
                )
            except Exception as conn_error:
                await channel.close()
                raise conn_error
                
        except asyncio.TimeoutError:
            return HealthCheckResult(
                service=service_id,
                status=HealthStatus.UNHEALTHY,
                response_time=self.timeout,
                details={"error": "gRPC请求超时"},
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                service=service_id,
                status=HealthStatus.UNHEALTHY,
                response_time=time.time() - start_time,
                details={"error": str(e)},
                timestamp=time.time()
            )


class RedisHealthChecker:
    """Redis健康检查器"""
    
    def __init__(self, timeout: float = 5.0):
        """
        初始化Redis健康检查器
        
        Args:
            timeout: 连接超时时间（秒）
        """
        self.timeout = timeout
        
    async def check(self, host: str = "localhost", port: int = 6379, 
                   password: Optional[str] = None, db: int = 0) -> HealthCheckResult:
        """
        检查Redis连接健康状态
        
        Args:
            host: Redis主机地址
            port: Redis端口
            password: Redis密码（可选）
            db: 数据库编号
            
        Returns:
            健康检查结果
        """
        start_time = time.time()
        service_name = f"redis://{host}:{port}/{db}"
        
        try:
            # 创建Redis连接
            redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                db=db,
                socket_timeout=self.timeout,
                socket_connect_timeout=self.timeout
            )
            
            # 执行ping命令
            await asyncio.wait_for(redis_client.ping(), timeout=self.timeout)
            
            # 获取Redis信息
            info = await redis_client.info()
            response_time = time.time() - start_time
            
            await redis_client.close()
            
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.HEALTHY,
                response_time=response_time,
                details={
                    "redis_version": info.get("redis_version"),
                    "connected_clients": info.get("connected_clients"),
                    "used_memory_human": info.get("used_memory_human"),
                    "uptime_in_seconds": info.get("uptime_in_seconds")
                },
                timestamp=time.time()
            )
            
        except asyncio.TimeoutError:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=self.timeout,
                details={"error": "Redis连接超时"},
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=time.time() - start_time,
                details={"error": str(e)},
                timestamp=time.time()
            )


class MongoHealthChecker:
    """MongoDB健康检查器"""
    
    def __init__(self, timeout: float = 5.0):
        """
        初始化MongoDB健康检查器
        
        Args:
            timeout: 连接超时时间（秒）
        """
        self.timeout = timeout
        
    async def check(self, uri: str) -> HealthCheckResult:
        """
        检查MongoDB连接健康状态
        
        Args:
            uri: MongoDB连接URI
            
        Returns:
            健康检查结果
        """
        start_time = time.time()
        service_name = f"mongodb://{uri}"
        
        try:
            # 创建MongoDB客户端
            client = motor.motor_asyncio.AsyncIOMotorClient(
                uri,
                serverSelectionTimeoutMS=int(self.timeout * 1000),
                connectTimeoutMS=int(self.timeout * 1000),
                socketTimeoutMS=int(self.timeout * 1000)
            )
            
            # 执行ping命令
            await asyncio.wait_for(
                client.admin.command("ping"),
                timeout=self.timeout
            )
            
            # 获取服务器状态
            server_status = await client.admin.command("serverStatus")
            response_time = time.time() - start_time
            
            client.close()
            
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.HEALTHY,
                response_time=response_time,
                details={
                    "version": server_status.get("version"),
                    "uptime": server_status.get("uptime"),
                    "connections": server_status.get("connections", {}).get("current"),
                    "host": server_status.get("host")
                },
                timestamp=time.time()
            )
            
        except asyncio.TimeoutError:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=self.timeout,
                details={"error": "MongoDB连接超时"},
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time=time.time() - start_time,
                details={"error": str(e)},
                timestamp=time.time()
            )


class HealthCheckManager:
    """健康检查管理器"""
    
    def __init__(self):
        """初始化健康检查管理器"""
        self.http_checker = HttpHealthChecker()
        self.grpc_checker = GrpcHealthChecker()
        self.redis_checker = RedisHealthChecker()
        self.mongo_checker = MongoHealthChecker()
        
    async def check_service_health(self, config: Dict[str, Any]) -> List[HealthCheckResult]:
        """
        检查所有服务的健康状态
        
        Args:
            config: 服务配置字典
            
        Returns:
            所有服务的健康检查结果列表
        """
        results = []
        
        # 检查游戏服务健康状态
        services = config.get("services", {})
        for service_name, service_config in services.items():
            instances = service_config.get("instances", 1)
            start_port = service_config.get("start_port", 8000)
            
            for i in range(instances):
                port = start_port + i
                if service_name == "gateway":
                    # HTTP健康检查
                    url = f"http://localhost:{port}/health"
                    result = await self.http_checker.check(url)
                else:
                    # gRPC健康检查
                    address = f"localhost:{port}"
                    result = await self.grpc_checker.check(address, service_name)
                
                results.append(result)
        
        # 检查Redis健康状态
        redis_config = config.get("redis", {})
        if redis_config:
            redis_result = await self.redis_checker.check(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379)
            )
            results.append(redis_result)
        
        # 检查MongoDB健康状态
        mongodb_config = config.get("mongodb", {})
        if mongodb_config:
            uri = mongodb_config.get("uri", "mongodb://localhost:27017/game")
            mongo_result = await self.mongo_checker.check(uri)
            results.append(mongo_result)
        
        return results
    
    async def wait_for_services_healthy(self, config: Dict[str, Any], 
                                      max_attempts: int = 30, 
                                      check_interval: float = 2.0) -> bool:
        """
        等待所有服务变为健康状态
        
        Args:
            config: 服务配置字典
            max_attempts: 最大检查次数
            check_interval: 检查间隔（秒）
            
        Returns:
            是否所有服务都健康
        """
        for attempt in range(max_attempts):
            logger.info(f"健康检查第 {attempt + 1} 次尝试...")
            
            results = await self.check_service_health(config)
            healthy_count = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
            total_count = len(results)
            
            logger.info(f"健康状态: {healthy_count}/{total_count} 服务正常")
            
            if healthy_count == total_count:
                logger.info("所有服务健康检查通过!")
                return True
            
            # 显示不健康的服务
            unhealthy_services = [r for r in results if r.status != HealthStatus.HEALTHY]
            for result in unhealthy_services:
                logger.warning(f"服务 {result.service} 不健康: {result.details.get('error', '未知错误')}")
            
            if attempt < max_attempts - 1:
                await asyncio.sleep(check_interval)
        
        logger.error(f"健康检查失败: 在 {max_attempts} 次尝试后仍有服务不健康")
        return False
    
    def get_health_summary(self, results: List[HealthCheckResult]) -> Dict[str, Any]:
        """
        获取健康检查摘要
        
        Args:
            results: 健康检查结果列表
            
        Returns:
            健康检查摘要
        """
        healthy_count = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
        total_count = len(results)
        avg_response_time = sum(r.response_time for r in results) / total_count if results else 0
        
        return {
            "total_services": total_count,
            "healthy_services": healthy_count,
            "unhealthy_services": total_count - healthy_count,
            "health_percentage": (healthy_count / total_count * 100) if total_count > 0 else 0,
            "average_response_time": avg_response_time,
            "timestamp": time.time(),
            "details": [
                {
                    "service": r.service,
                    "status": r.status.value,
                    "response_time": r.response_time,
                    "details": r.details
                }
                for r in results
            ]
        }


async def main():
    """测试函数"""
    health_manager = HealthCheckManager()
    
    # 测试配置
    config = {
        "services": {
            "gateway": {"instances": 1, "start_port": 8000},
            "logic": {"instances": 1, "start_port": 9000}
        },
        "redis": {"host": "localhost", "port": 6379},
        "mongodb": {"uri": "mongodb://localhost:27017/game"}
    }
    
    # 执行健康检查
    results = await health_manager.check_service_health(config)
    summary = health_manager.get_health_summary(results)
    
    print("健康检查结果:")
    for result in results:
        print(f"  {result.service}: {result.status.value} ({result.response_time:.3f}s)")
    
    print(f"\n摘要: {summary['healthy_services']}/{summary['total_services']} 服务健康")


if __name__ == "__main__":
    asyncio.run(main())