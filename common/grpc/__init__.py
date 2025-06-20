"""
gRPC服务模块
gRPC Service Module

作者: lx
日期: 2025-06-18
描述: gRPC服务定义和客户端/服务端实现
"""

# 导入核心组件
from .grpc_client import GrpcClient, grpc_call, get_grpc_client, close_all_clients
from .grpc_service import (
    grpc_service, grpc_method, GameServiceServicer,
    start_grpc_server, register_service_instance,
    get_service_registry, get_service_stats
)
from .grpc_pool import GrpcConnectionPool, get_connection_pool, close_global_pool

# 导出的公共接口
__all__ = [
    # 客户端
    "GrpcClient",
    "grpc_call",
    "get_grpc_client", 
    "close_all_clients",
    
    # 服务端
    "grpc_service",
    "grpc_method",
    "GameServiceServicer",
    "start_grpc_server",
    "register_service_instance",
    "get_service_registry",
    "get_service_stats",
    
    # 连接池
    "GrpcConnectionPool",
    "get_connection_pool",
    "close_global_pool"
]