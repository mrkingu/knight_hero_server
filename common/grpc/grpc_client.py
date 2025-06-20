"""
gRPC客户端模块
gRPC Client Module

作者: lx
日期: 2025-06-18
描述: 提供异步gRPC客户端，支持超时控制、重试机制、熔断器模式
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from enum import Enum
import grpc
from contextlib import asynccontextmanager

from .protos import service_pb2, service_pb2_grpc
from .grpc_pool import get_connection_pool
import orjson


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态枚举"""
    CLOSED = "closed"       # 正常状态
    OPEN = "open"          # 熔断状态
    HALF_OPEN = "half_open" # 半开状态


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5          # 失败阈值
    recovery_timeout: float = 30.0      # 恢复超时时间(秒)
    success_threshold: int = 3          # 半开状态成功阈值
    window_size: int = 100             # 滑动窗口大小


@dataclass 
class CircuitBreakerStats:
    """熔断器统计信息"""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    
    # 滑动窗口
    recent_results: List[bool] = field(default_factory=list)


class CircuitBreaker:
    """
    熔断器实现
    
    功能特性:
    1. 失败次数达到阈值时开启熔断
    2. 恢复超时后进入半开状态
    3. 半开状态成功次数达到阈值后关闭熔断
    4. 滑动窗口统计最近请求结果
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.stats = CircuitBreakerStats()
        
    async def call(self, func, *args, **kwargs):
        """
        通过熔断器执行函数调用
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            CircuitBreakerOpenError: 熔断器开启时抛出
        """
        # 检查熔断器状态
        if self.stats.state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if time.time() - self.stats.last_failure_time >= self.config.recovery_timeout:
                self.stats.state = CircuitState.HALF_OPEN
                self.stats.success_count = 0
                logger.info("熔断器进入半开状态")
            else:
                raise CircuitBreakerOpenError("熔断器处于开启状态")
        
        self.stats.total_requests += 1
        
        try:
            # 执行函数调用
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 记录成功
            self._record_success()
            return result
            
        except Exception as e:
            # 记录失败
            self._record_failure()
            raise e
    
    def _record_success(self):
        """记录成功调用"""
        self.stats.success_count += 1
        self.stats.last_success_time = time.time()
        
        # 更新滑动窗口
        self._update_window(True)
        
        # 检查状态转换
        if self.stats.state == CircuitState.HALF_OPEN:
            if self.stats.success_count >= self.config.success_threshold:
                self.stats.state = CircuitState.CLOSED
                self.stats.failure_count = 0
                logger.info("熔断器关闭")
    
    def _record_failure(self):
        """记录失败调用"""
        self.stats.failure_count += 1
        self.stats.total_failures += 1
        self.stats.last_failure_time = time.time()
        
        # 更新滑动窗口
        self._update_window(False)
        
        # 检查是否需要开启熔断
        if (self.stats.state == CircuitState.CLOSED and 
            self.stats.failure_count >= self.config.failure_threshold):
            self.stats.state = CircuitState.OPEN
            logger.warning("熔断器开启")
        elif self.stats.state == CircuitState.HALF_OPEN:
            self.stats.state = CircuitState.OPEN
            logger.warning("半开状态失败，熔断器重新开启")
    
    def _update_window(self, success: bool):
        """更新滑动窗口"""
        self.stats.recent_results.append(success)
        
        # 保持窗口大小
        if len(self.stats.recent_results) > self.config.window_size:
            self.stats.recent_results.pop(0)
    
    def get_stats(self) -> Dict:
        """获取熔断器统计信息"""
        recent_failure_rate = 0.0
        if self.stats.recent_results:
            failures = sum(1 for r in self.stats.recent_results if not r)
            recent_failure_rate = failures / len(self.stats.recent_results)
        
        return {
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_requests": self.stats.total_requests,
            "total_failures": self.stats.total_failures,
            "recent_failure_rate": recent_failure_rate,
            "window_size": len(self.stats.recent_results),
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time
        }


class CircuitBreakerOpenError(Exception):
    """熔断器开启异常"""
    pass


class GrpcClient:
    """
    异步gRPC客户端
    
    功能特性:
    1. 异步RPC调用
    2. 超时控制(默认3秒)  
    3. 重试机制
    4. 熔断器模式
    5. 连接池管理
    6. 自动序列化/反序列化
    """
    
    def __init__(
        self,
        service_address: str,
        default_timeout: float = 3.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        """
        初始化gRPC客户端
        
        Args:
            service_address: 服务地址 (host:port)
            default_timeout: 默认超时时间(秒)
            max_retries: 最大重试次数
            retry_delay: 重试延迟(秒)
            circuit_breaker_config: 熔断器配置
        """
        self.service_address = service_address
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 获取连接池
        self.pool = get_connection_pool()
        
        # 初始化熔断器
        if circuit_breaker_config is None:
            circuit_breaker_config = CircuitBreakerConfig()
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config)
        
        # 统计信息
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "timeout_calls": 0,
            "retry_calls": 0,
            "circuit_breaker_calls": 0,
            "total_time": 0.0
        }
        
        logger.debug(f"gRPC客户端初始化: {service_address}")

    @asynccontextmanager
    async def _get_stub(self):
        """获取gRPC stub (上下文管理器)"""
        channel = await self.pool.get_channel(self.service_address)
        if not channel:
            raise ConnectionError(f"无法获取连接: {self.service_address}")
        
        stub = service_pb2_grpc.GameServiceStub(channel)
        try:
            yield stub
        finally:
            # 连接池会自动管理连接，这里不需要手动关闭
            pass

    async def call(
        self,
        method_name: str,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Any:
        """
        执行RPC调用
        
        Args:
            method_name: 方法名
            timeout: 超时时间(秒)，不指定则使用默认值
            **kwargs: 方法参数
            
        Returns:
            RPC调用结果
            
        Raises:
            ConnectionError: 连接失败
            TimeoutError: 调用超时
            CircuitBreakerOpenError: 熔断器开启
            Exception: 其他异常
        """
        if timeout is None:
            timeout = self.default_timeout
        
        # 解析服务名 (从地址中推断或使用方法名前缀)
        service_name = self._extract_service_name(method_name)
        
        start_time = time.time()
        self.stats["total_calls"] += 1
        
        try:
            # 通过熔断器执行调用
            result = await self.circuit_breaker.call(
                self._execute_call,
                service_name,
                method_name,
                timeout,
                kwargs
            )
            
            # 更新统计
            self.stats["successful_calls"] += 1
            self.stats["total_time"] += time.time() - start_time
            
            return result
            
        except CircuitBreakerOpenError:
            self.stats["circuit_breaker_calls"] += 1
            logger.warning(f"熔断器阻止调用: {method_name}")
            raise
            
        except asyncio.TimeoutError:
            self.stats["timeout_calls"] += 1
            self.stats["failed_calls"] += 1
            logger.error(f"RPC调用超时: {method_name} (timeout={timeout}s)")
            raise TimeoutError(f"RPC调用超时: {method_name}")
            
        except Exception as e:
            self.stats["failed_calls"] += 1
            logger.error(f"RPC调用失败: {method_name} - {e}")
            raise

    async def _execute_call(
        self,
        service_name: str,
        method_name: str,
        timeout: float,
        kwargs: Dict[str, Any]
    ) -> Any:
        """执行实际的RPC调用（带重试）"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # 提取纯方法名（去掉服务名前缀）
                pure_method_name = method_name.split('.')[-1] if '.' in method_name else method_name
                
                # 创建请求
                request = service_pb2.RpcRequest(
                    service_name=service_name,
                    method_name=pure_method_name,
                    payload=orjson.dumps(kwargs) if kwargs else b"",
                    metadata={}
                )
                
                # 执行调用
                async with self._get_stub() as stub:
                    response = await asyncio.wait_for(
                        stub.Call(request),
                        timeout=timeout
                    )
                
                # 检查响应状态
                if response.code != 0:
                    raise Exception(f"RPC错误 (code={response.code}): {response.message}")
                
                # 反序列化结果
                if response.payload:
                    result = orjson.loads(response.payload)
                else:
                    result = None
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # 最后一次尝试，不再重试
                if attempt == self.max_retries:
                    break
                
                # 记录重试
                self.stats["retry_calls"] += 1
                logger.warning(f"RPC调用失败，重试 {attempt + 1}/{self.max_retries}: {method_name} - {e}")
                
                # 等待重试延迟
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        # 所有重试都失败了
        raise last_exception

    def _extract_service_name(self, method_name: str) -> str:
        """
        从方法名中提取服务名
        
        支持格式:
        1. "service.method" -> "service"
        2. "method" -> 从地址推断服务名
        """
        if '.' in method_name:
            return method_name.split('.')[0]
        
        # 从地址推断服务名 (假设地址格式为 service-name:port)
        host = self.service_address.split(':')[0]
        if '-' in host:
            return host.split('-')[0]
        
        # 默认使用主机名作为服务名
        return host

    async def stream_call(
        self,
        method_name: str,
        request_stream: List[Dict[str, Any]],
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        执行流式RPC调用
        
        Args:
            method_name: 方法名
            request_stream: 请求流
            timeout: 超时时间
            
        Returns:
            响应流
        """
        if timeout is None:
            timeout = self.default_timeout * len(request_stream)
        
        service_name = self._extract_service_name(method_name)
        
        try:
            # 创建请求流
            async def request_generator():
                for request_data in request_stream:
                    yield service_pb2.RpcRequest(
                        service_name=service_name,
                        method_name=method_name,
                        payload=orjson.dumps(request_data) if request_data else b"",
                        metadata={}
                    )
            
            # 执行流式调用
            async with self._get_stub() as stub:
                response_stream = stub.StreamCall(request_generator())
                
                results = []
                async for response in response_stream:
                    if response.code != 0:
                        raise Exception(f"RPC错误 (code={response.code}): {response.message}")
                    
                    if response.payload:
                        result = orjson.loads(response.payload)
                    else:
                        result = None
                    
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"流式RPC调用失败: {method_name} - {e}")
            raise

    def get_stats(self) -> Dict:
        """获取客户端统计信息"""
        return {
            "client_stats": self.stats.copy(),
            "circuit_breaker_stats": self.circuit_breaker.get_stats(),
            "service_address": self.service_address,
            "config": {
                "default_timeout": self.default_timeout,
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay
            }
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
        return False
    
    async def close(self):
        """关闭客户端，清理资源"""
        # gRPC客户端本身不需要特殊清理，连接池会自动管理
        # 这里只是为了接口完整性
        logger.debug(f"gRPC客户端关闭: {self.service_address}")


# 便捷函数
async def grpc_call(
    service_address: str,
    method_name: str,
    timeout: float = 3.0,
    **kwargs
) -> Any:
    """
    便捷的gRPC调用函数
    
    Args:
        service_address: 服务地址
        method_name: 方法名
        timeout: 超时时间
        **kwargs: 方法参数
        
    Returns:
        调用结果
    """
    client = GrpcClient(service_address, default_timeout=timeout)
    return await client.call(method_name, **kwargs)


# 全局客户端缓存
_client_cache: Dict[str, GrpcClient] = {}


def get_grpc_client(service_address: str) -> GrpcClient:
    """
    获取gRPC客户端实例 (带缓存)
    
    Args:
        service_address: 服务地址
        
    Returns:
        gRPC客户端实例
    """
    if service_address not in _client_cache:
        _client_cache[service_address] = GrpcClient(service_address)
    
    return _client_cache[service_address]


async def close_all_clients():
    """关闭所有客户端缓存"""
    global _client_cache
    _client_cache.clear()
    logger.info("所有gRPC客户端已清理")