"""
Gateway性能测试脚本
Gateway Performance Test Script

作者: lx  
日期: 2025-06-18
描述: 测试Gateway服务的10K+连接性能
"""
import asyncio
import time
from unittest.mock import Mock
from services.gateway.connection_manager import ConnectionManager, ConnectionPoolConfig
from services.gateway.session_manager import SessionManager, SessionManagerConfig


async def test_10k_connections():
    """测试10K连接性能"""
    print("开始10K连接性能测试...")
    
    # 配置连接池
    pool_config = ConnectionPoolConfig(
        POOL_SIZE=10000,
        PRE_ALLOCATE_SIZE=10000,
        MAX_CONCURRENT_CONNECTIONS=10000,
        ALLOCATION_BATCH_SIZE=1000
    )
    
    # 配置会话管理器
    session_config = SessionManagerConfig(
        LOCAL_CACHE_SIZE=10000
    )
    
    # 创建管理器
    connection_manager = ConnectionManager(pool_config)
    session_manager = SessionManager(session_config)
    
    try:
        # 初始化
        start_time = time.time()
        print("初始化连接管理器...")
        await connection_manager.initialize()
        init_time = time.time() - start_time
        print(f"连接管理器初始化完成，耗时: {init_time:.2f}秒")
        
        # 检查预分配连接数
        pool_stats = connection_manager.get_pool_stats()
        print(f"预分配连接数: {pool_stats['idle_connections']}")
        
        # 模拟创建连接
        print("开始创建连接...")
        connections = []
        create_start = time.time()
        
        # 分批创建连接以避免内存压力
        batch_size = 1000
        for batch in range(0, 10000, batch_size):  # 测试10K连接
            batch_connections = []
            for i in range(batch_size):
                # 创建模拟WebSocket
                mock_websocket = Mock()
                mock_websocket.client = Mock()
                mock_websocket.client.host = f"192.168.1.{i % 255}"
                mock_websocket.client.port = 12345 + i
                mock_websocket.accept = Mock(return_value=asyncio.Future())
                mock_websocket.accept.return_value.set_result(None)
                
                # 创建连接
                connection = await connection_manager.create_connection(mock_websocket)
                if connection:
                    batch_connections.append(connection)
            
            connections.extend(batch_connections)
            
            if (batch + batch_size) % 1000 == 0:
                print(f"已创建 {len(connections)} 个连接")
        
        create_time = time.time() - create_start
        print(f"连接创建完成，总数: {len(connections)}, 耗时: {create_time:.2f}秒")
        print(f"平均每秒创建连接数: {len(connections) / create_time:.0f}")
        
        # 获取最终统计
        final_stats = connection_manager.get_pool_stats()
        print(f"\n最终统计:")
        print(f"- 活跃连接: {final_stats['active_connections']}")
        print(f"- 空闲连接: {final_stats['idle_connections']}")
        print(f"- 总创建数: {final_stats['total_created']}")
        print(f"- 峰值并发: {final_stats['peak_concurrent']}")
        print(f"- 缓存命中率: {final_stats['hit_rate']:.2%}")
        
        # 清理测试
        print("\n开始清理连接...")
        cleanup_start = time.time()
        
        for connection in connections:
            await connection_manager.release_connection(connection)
        
        cleanup_time = time.time() - cleanup_start
        print(f"连接清理完成，耗时: {cleanup_time:.2f}秒")
        
    finally:
        # 关闭管理器
        await connection_manager.shutdown()
        await session_manager.shutdown()
    
    print("10K连接性能测试完成")


async def test_session_performance():
    """测试会话性能"""
    print("\n开始会话性能测试...")
    
    session_config = SessionManagerConfig(
        LOCAL_CACHE_SIZE=5000,
        DEFAULT_SESSION_TTL=30 * 60
    )
    
    session_manager = SessionManager(session_config)
    
    try:
        # 创建模拟连接
        mock_connections = []
        for i in range(1000):
            mock_conn = Mock()
            mock_conn.id = i
            mock_connections.append(mock_conn)
        
        # 创建会话
        print("创建1000个会话...")
        start_time = time.time()
        sessions = []
        
        for i, mock_conn in enumerate(mock_connections):
            session = await session_manager.create_session(mock_conn)
            if session:
                sessions.append(session)
                
                # 认证部分会话
                if i % 2 == 0:
                    await session_manager.authenticate_session(
                        session.id, 
                        f"user_{i}",
                        device_id=f"device_{i}"
                    )
        
        create_time = time.time() - start_time
        print(f"会话创建完成，总数: {len(sessions)}, 耗时: {create_time:.2f}秒")
        
        # 测试会话查询性能
        print("测试会话查询性能...")
        query_start = time.time()
        
        for _ in range(1000):
            session_id = sessions[_ % len(sessions)].id
            await session_manager.get_session(session_id)
        
        query_time = time.time() - query_start
        print(f"1000次查询耗时: {query_time:.2f}秒")
        print(f"平均查询时间: {query_time * 1000 / 1000:.2f}ms")
        
        # 获取统计
        stats = session_manager.get_stats()
        print(f"\n会话管理器统计:")
        print(f"- 活跃会话: {stats['active_sessions']}")
        print(f"- 缓存会话: {stats['cached_sessions']}")
        print(f"- 缓存命中率: {stats['cache_hit_rate']:.2%}")
        
    finally:
        await session_manager.shutdown()
    
    print("会话性能测试完成")


async def main():
    """主测试函数"""
    print("=== Gateway服务性能测试 ===\n")
    
    # 测试连接性能
    await test_10k_connections()
    
    # 测试会话性能  
    await test_session_performance()
    
    print("\n=== 所有性能测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())