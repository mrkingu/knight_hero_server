"""
gRPC服务框架使用示例
演示如何使用装饰器定义服务和客户端调用
作者: lx
日期: 2025-06-18
"""
import asyncio
import logging
from typing import Dict, Any

# 设置日志
logging.basicConfig(level=logging.INFO)

# 导入gRPC框架
from common.grpc import (
    grpc_service, grpc_method, GrpcClient,
    start_grpc_server, register_service_instance
)


# 定义逻辑服务
@grpc_service("logic", address="localhost", port=50051)
class LogicService:
    """逻辑服务RPC接口"""
    
    def __init__(self):
        # 模拟数据存储
        self.players = {
            "123": {"player_id": "123", "level": 10, "gold": 1000, "diamond": 50},
            "456": {"player_id": "456", "level": 25, "gold": 5000, "diamond": 200}
        }
    
    @grpc_method(timeout=2.0, description="获取玩家信息")
    async def get_player_info(self, player_id: str) -> Dict[str, Any]:
        """获取玩家信息"""
        await asyncio.sleep(0.1)  # 模拟数据库查询
        
        if player_id in self.players:
            return self.players[player_id]
        else:
            raise ValueError(f"玩家不存在: {player_id}")
    
    @grpc_method(timeout=3.0, description="更新玩家等级")
    async def update_player_level(self, player_id: str, new_level: int) -> bool:
        """更新玩家等级"""
        await asyncio.sleep(0.2)  # 模拟数据库更新
        
        if player_id in self.players:
            self.players[player_id]["level"] = new_level
            return True
        else:
            raise ValueError(f"玩家不存在: {player_id}")
    
    @grpc_method(description="添加玩家资源")
    async def add_resources(self, player_id: str, gold: int = 0, diamond: int = 0) -> Dict[str, int]:
        """添加玩家资源"""
        if player_id in self.players:
            player = self.players[player_id]
            player["gold"] += gold
            player["diamond"] += diamond
            
            return {
                "gold": player["gold"],
                "diamond": player["diamond"]
            }
        else:
            raise ValueError(f"玩家不存在: {player_id}")


# 定义聊天服务
@grpc_service("chat", address="localhost", port=50052)
class ChatService:
    """聊天服务RPC接口"""
    
    def __init__(self):
        self.messages = []
    
    @grpc_method(timeout=1.0, description="发送消息")
    async def send_message(self, player_id: str, content: str, channel: str = "world") -> bool:
        """发送聊天消息"""
        message = {
            "player_id": player_id,
            "content": content,
            "channel": channel,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        self.messages.append(message)
        print(f"[{channel}] {player_id}: {content}")
        return True
    
    @grpc_method(description="获取最近消息")
    async def get_recent_messages(self, channel: str = "world", limit: int = 10) -> list:
        """获取最近的聊天消息"""
        channel_messages = [
            msg for msg in self.messages 
            if msg["channel"] == channel
        ]
        
        return channel_messages[-limit:]


async def run_server_example():
    """运行服务端示例"""
    print("=== gRPC服务端示例 ===")
    
    # 创建服务实例
    logic_service = LogicService()
    chat_service = ChatService()
    
    # 注册服务实例
    register_service_instance("logic", logic_service)
    register_service_instance("chat", chat_service)
    
    # 启动gRPC服务器
    server = await start_grpc_server(address="localhost", port=50051)
    
    print("gRPC服务器已启动，监听端口 50051")
    print("服务列表:")
    print("- logic: 逻辑服务")
    print("- chat: 聊天服务")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("正在关闭服务器...")
        await server.stop(grace=5)


async def run_client_example():
    """运行客户端示例"""
    print("=== gRPC客户端示例 ===")
    
    try:
        # 创建客户端
        async with GrpcClient("localhost:50051") as client:
            
            # 1. 获取玩家信息
            print("\n1. 获取玩家信息:")
            try:
                player_info = await client.call("get_player_info", player_id="123")
                print(f"玩家信息: {player_info}")
            except Exception as e:
                print(f"获取玩家信息失败: {e}")
            
            # 2. 更新玩家等级
            print("\n2. 更新玩家等级:")
            try:
                success = await client.call("update_player_level", player_id="123", new_level=15)
                print(f"更新等级结果: {success}")
            except Exception as e:
                print(f"更新等级失败: {e}")
            
            # 3. 添加资源
            print("\n3. 添加玩家资源:")
            try:
                resources = await client.call("add_resources", player_id="123", gold=500, diamond=10)
                print(f"当前资源: {resources}")
            except Exception as e:
                print(f"添加资源失败: {e}")
            
            # 4. 获取更新后的玩家信息
            print("\n4. 获取更新后的玩家信息:")
            try:
                updated_info = await client.call("get_player_info", player_id="123")
                print(f"更新后信息: {updated_info}")
            except Exception as e:
                print(f"获取更新信息失败: {e}")
            
            # 5. 测试不存在的玩家
            print("\n5. 测试不存在的玩家:")
            try:
                invalid_info = await client.call("get_player_info", player_id="999")
                print(f"不存在玩家信息: {invalid_info}")
            except Exception as e:
                print(f"预期的错误: {e}")
            
            # 6. 测试客户端统计
            print("\n6. 客户端统计信息:")
            stats = client.get_stats()
            print(f"调用统计: {stats['client_stats']}")
            print(f"熔断器状态: {stats['circuit_breaker_stats']['state']}")
        
    except Exception as e:
        print(f"客户端示例失败: {e}")


async def run_load_test():
    """运行负载测试"""
    print("=== gRPC负载测试 ===")
    
    async def single_request(client, request_id):
        """单个请求"""
        try:
            result = await client.call("get_player_info", player_id="123")
            return f"请求{request_id}: 成功"
        except Exception as e:
            return f"请求{request_id}: 失败 - {e}"
    
    # 创建客户端
    client = GrpcClient("localhost:50051")
    
    # 并发发送100个请求
    print("发送100个并发请求...")
    start_time = asyncio.get_event_loop().time()
    
    tasks = [single_request(client, i) for i in range(100)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = asyncio.get_event_loop().time()
    
    # 统计结果
    success_count = sum(1 for r in results if "成功" in str(r))
    failure_count = len(results) - success_count
    total_time = end_time - start_time
    
    print(f"负载测试结果:")
    print(f"- 总请求数: {len(results)}")
    print(f"- 成功请求: {success_count}")
    print(f"- 失败请求: {failure_count}")
    print(f"- 总耗时: {total_time:.2f}秒")
    print(f"- 平均QPS: {len(results)/total_time:.2f}")
    
    # 显示客户端统计
    stats = client.get_stats()
    print(f"\n客户端统计:")
    print(f"- 总调用次数: {stats['client_stats']['total_calls']}")
    print(f"- 成功调用: {stats['client_stats']['successful_calls']}")
    print(f"- 失败调用: {stats['client_stats']['failed_calls']}")


def print_framework_info():
    """打印框架信息"""
    print("=== Knight Hero gRPC服务框架 ===")
    print("功能特性:")
    print("✅ 异步gRPC支持")
    print("✅ 装饰器自动注册")
    print("✅ 连接池管理")
    print("✅ 健康检查")
    print("✅ 负载均衡")
    print("✅ 熔断器模式")
    print("✅ 重试机制")
    print("✅ 超时控制")
    print("✅ 统计监控")
    print("✅ 自动序列化")
    print()


if __name__ == "__main__":
    print_framework_info()
    
    import sys
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
        if mode == "server":
            asyncio.run(run_server_example())
        elif mode == "client":
            asyncio.run(run_client_example())
        elif mode == "load":
            asyncio.run(run_load_test())
        else:
            print("用法:")
            print("  python examples/grpc_example.py server   # 运行服务端")
            print("  python examples/grpc_example.py client   # 运行客户端")
            print("  python examples/grpc_example.py load     # 运行负载测试")
    else:
        print("用法:")
        print("  python examples/grpc_example.py server   # 运行服务端")
        print("  python examples/grpc_example.py client   # 运行客户端") 
        print("  python examples/grpc_example.py load     # 运行负载测试")