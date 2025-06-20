"""
Mock客户端工具
Mock Client Utilities

作者: lx
日期: 2025-06-18
描述: WebSocket客户端、自动消息构造、批量测试、结果统计
"""

import asyncio
import websockets
import json
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型枚举"""
    LOGIN = 1001
    LOGIN_RESPONSE = 1002
    LOGOUT = 1003
    PLAYER_INFO = 1010
    PLAYER_INFO_RESPONSE = 1011
    CHAT = 2001
    CHAT_RESPONSE = 2002
    BATTLE_START = 3001
    BATTLE_RESPONSE = 3002
    MOVE = 4001
    MOVE_RESPONSE = 4002
    USE_ITEM = 5001
    USE_ITEM_RESPONSE = 5002
    HEARTBEAT = 9001
    HEARTBEAT_RESPONSE = 9002


@dataclass
class TestResult:
    """测试结果数据类"""
    client_id: str
    success: bool
    response_time: float
    message_type: str
    error_message: Optional[str] = None
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class BatchTestStats:
    """批量测试统计"""
    total_clients: int
    successful_clients: int
    failed_clients: int
    total_messages: int
    successful_messages: int
    failed_messages: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    total_duration: float
    messages_per_second: float
    clients_per_second: float
    error_rate: float
    detailed_results: List[TestResult] = field(default_factory=list)


class MockWebSocketClient:
    """Mock WebSocket客户端"""
    
    def __init__(self, 
                 url: str = "ws://localhost:8000/ws",
                 client_id: str = None,
                 timeout: float = 30.0):
        self.url = url
        self.client_id = client_id or f"mock_client_{uuid.uuid4().hex[:8]}"
        self.timeout = timeout
        self.websocket = None
        self.connected = False
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "connection_time": 0,
            "total_response_time": 0,
            "errors": 0
        }
        self.message_history = []
        
    async def connect(self) -> bool:
        """连接WebSocket服务器"""
        try:
            start_time = time.time()
            self.websocket = await websockets.connect(
                self.url,
                timeout=self.timeout,
                ping_interval=30,
                ping_timeout=10
            )
            self.stats["connection_time"] = time.time() - start_time
            self.connected = True
            logger.info(f"Client {self.client_id} connected to {self.url}")
            return True
        except Exception as e:
            logger.error(f"Client {self.client_id} connection failed: {e}")
            self.stats["errors"] += 1
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket and self.connected:
            try:
                await self.websocket.close()
                self.connected = False
                logger.info(f"Client {self.client_id} disconnected")
            except Exception as e:
                logger.error(f"Client {self.client_id} disconnect error: {e}")
    
    async def send_message(self, message: Dict[str, Any]) -> bool:
        """发送消息"""
        if not self.connected or not self.websocket:
            return False
        
        try:
            message_json = json.dumps(message)
            await self.websocket.send(message_json)
            self.stats["messages_sent"] += 1
            self.message_history.append({
                "type": "sent",
                "message": message,
                "timestamp": time.time()
            })
            return True
        except Exception as e:
            logger.error(f"Client {self.client_id} send error: {e}")
            self.stats["errors"] += 1
            return False
    
    async def receive_message(self, timeout: float = None) -> Optional[Dict[str, Any]]:
        """接收消息"""
        if not self.connected or not self.websocket:
            return None
        
        try:
            timeout = timeout or self.timeout
            message = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=timeout
            )
            data = json.loads(message)
            self.stats["messages_received"] += 1
            self.message_history.append({
                "type": "received",
                "message": data,
                "timestamp": time.time()
            })
            return data
        except asyncio.TimeoutError:
            logger.warning(f"Client {self.client_id} receive timeout")
            return None
        except Exception as e:
            logger.error(f"Client {self.client_id} receive error: {e}")
            self.stats["errors"] += 1
            return None
    
    async def send_and_wait_response(self, 
                                   message: Dict[str, Any],
                                   timeout: float = 5.0) -> TestResult:
        """发送消息并等待响应"""
        start_time = time.time()
        success = await self.send_message(message)
        
        if not success:
            return TestResult(
                client_id=self.client_id,
                success=False,
                response_time=time.time() - start_time,
                message_type=str(message.get("msg_id", "unknown")),
                error_message="Failed to send message",
                request_data=message
            )
        
        response = await self.receive_message(timeout=timeout)
        response_time = time.time() - start_time
        self.stats["total_response_time"] += response_time
        
        if response:
            return TestResult(
                client_id=self.client_id,
                success=True,
                response_time=response_time,
                message_type=str(message.get("msg_id", "unknown")),
                request_data=message,
                response_data=response
            )
        else:
            return TestResult(
                client_id=self.client_id,
                success=False,
                response_time=response_time,
                message_type=str(message.get("msg_id", "unknown")),
                error_message="No response received",
                request_data=message
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息"""
        stats = self.stats.copy()
        if stats["messages_received"] > 0:
            stats["avg_response_time"] = stats["total_response_time"] / stats["messages_received"]
        else:
            stats["avg_response_time"] = 0
        return stats


class MessageBuilder:
    """消息构建器"""
    
    @staticmethod
    def create_login_message(user_id: str, player_id: str, device_id: str = None) -> Dict[str, Any]:
        """创建登录消息"""
        return {
            "msg_id": MessageType.LOGIN.value,
            "player_id": player_id,
            "data": {
                "user_id": user_id,
                "device_id": device_id or f"device_{uuid.uuid4().hex[:8]}",
                "version": "1.0.0",
                "platform": "test"
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
    
    @staticmethod
    def create_chat_message(player_id: str, content: str, channel: str = "world") -> Dict[str, Any]:
        """创建聊天消息"""
        return {
            "msg_id": MessageType.CHAT.value,
            "player_id": player_id,
            "data": {
                "content": content,
                "channel": channel,
                "timestamp": time.time()
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
    
    @staticmethod
    def create_player_info_query(player_id: str, query_type: str = "basic") -> Dict[str, Any]:
        """创建玩家信息查询消息"""
        return {
            "msg_id": MessageType.PLAYER_INFO.value,
            "player_id": player_id,
            "data": {
                "query_type": query_type,
                "include_stats": True,
                "include_inventory": False
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
    
    @staticmethod
    def create_battle_message(player_id: str, target_id: str, battle_type: str = "pve") -> Dict[str, Any]:
        """创建战斗消息"""
        return {
            "msg_id": MessageType.BATTLE_START.value,
            "player_id": player_id,
            "data": {
                "target_id": target_id,
                "battle_type": battle_type,
                "location": {"x": 100, "y": 200, "z": 0}
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
    
    @staticmethod
    def create_heartbeat_message(player_id: str) -> Dict[str, Any]:
        """创建心跳消息"""
        return {
            "msg_id": MessageType.HEARTBEAT.value,
            "player_id": player_id,
            "data": {
                "timestamp": time.time()
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }


class BatchTestRunner:
    """批量测试运行器"""
    
    def __init__(self, 
                 server_url: str = "ws://localhost:8000/ws",
                 max_concurrent: int = 100):
        self.server_url = server_url
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_single_client_test(self, 
                                   client_id: str,
                                   test_scenario: Callable[[MockWebSocketClient], Any]) -> List[TestResult]:
        """运行单个客户端测试"""
        async with self.semaphore:
            client = MockWebSocketClient(url=self.server_url, client_id=client_id)
            results = []
            
            try:
                # 连接
                if not await client.connect():
                    results.append(TestResult(
                        client_id=client_id,
                        success=False,
                        response_time=0,
                        message_type="connection",
                        error_message="Failed to connect"
                    ))
                    return results
                
                # 执行测试场景
                scenario_results = await test_scenario(client)
                if isinstance(scenario_results, list):
                    results.extend(scenario_results)
                elif isinstance(scenario_results, TestResult):
                    results.append(scenario_results)
                
            except Exception as e:
                results.append(TestResult(
                    client_id=client_id,
                    success=False,
                    response_time=0,
                    message_type="scenario",
                    error_message=str(e)
                ))
            finally:
                await client.disconnect()
            
            return results
    
    async def run_batch_test(self,
                           num_clients: int,
                           test_scenario: Callable[[MockWebSocketClient], Any]) -> BatchTestStats:
        """运行批量测试"""
        start_time = time.time()
        
        # 创建并发任务
        tasks = []
        for i in range(num_clients):
            client_id = f"batch_client_{i}"
            task = self.run_single_client_test(client_id, test_scenario)
            tasks.append(task)
        
        # 执行并发测试
        all_results = []
        for task in asyncio.as_completed(tasks):
            try:
                results = await task
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Task failed: {e}")
        
        total_duration = time.time() - start_time
        
        # 计算统计信息
        return self._calculate_stats(all_results, num_clients, total_duration)
    
    def _calculate_stats(self, 
                        results: List[TestResult], 
                        num_clients: int,
                        total_duration: float) -> BatchTestStats:
        """计算批量测试统计信息"""
        if not results:
            return BatchTestStats(
                total_clients=num_clients,
                successful_clients=0,
                failed_clients=num_clients,
                total_messages=0,
                successful_messages=0,
                failed_messages=0,
                avg_response_time=0,
                min_response_time=0,
                max_response_time=0,
                total_duration=total_duration,
                messages_per_second=0,
                clients_per_second=0,
                error_rate=100.0,
                detailed_results=results
            )
        
        # 统计成功和失败
        successful_messages = sum(1 for r in results if r.success)
        failed_messages = len(results) - successful_messages
        
        # 统计客户端
        client_ids = set(r.client_id for r in results)
        successful_clients = len(set(r.client_id for r in results if r.success))
        failed_clients = len(client_ids) - successful_clients
        
        # 响应时间统计
        response_times = [r.response_time for r in results if r.success]
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
        
        # 吞吐量统计
        messages_per_second = len(results) / total_duration if total_duration > 0 else 0
        clients_per_second = len(client_ids) / total_duration if total_duration > 0 else 0
        
        # 错误率
        error_rate = (failed_messages / len(results)) * 100 if results else 100
        
        return BatchTestStats(
            total_clients=num_clients,
            successful_clients=successful_clients,
            failed_clients=failed_clients,
            total_messages=len(results),
            successful_messages=successful_messages,
            failed_messages=failed_messages,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            total_duration=total_duration,
            messages_per_second=messages_per_second,
            clients_per_second=clients_per_second,
            error_rate=error_rate,
            detailed_results=results
        )


class TestScenarios:
    """测试场景集合"""
    
    @staticmethod
    async def simple_login_test(client: MockWebSocketClient) -> List[TestResult]:
        """简单登录测试"""
        user_id = f"test_user_{client.client_id}"
        player_id = f"test_player_{client.client_id}"
        
        login_msg = MessageBuilder.create_login_message(user_id, player_id)
        result = await client.send_and_wait_response(login_msg)
        
        return [result]
    
    @staticmethod
    async def chat_flood_test(client: MockWebSocketClient) -> List[TestResult]:
        """聊天消息洪水测试"""
        user_id = f"test_user_{client.client_id}"
        player_id = f"test_player_{client.client_id}"
        results = []
        
        # 先登录
        login_msg = MessageBuilder.create_login_message(user_id, player_id)
        login_result = await client.send_and_wait_response(login_msg)
        results.append(login_result)
        
        if login_result.success:
            # 发送多条聊天消息
            for i in range(10):
                chat_msg = MessageBuilder.create_chat_message(
                    player_id, 
                    f"Chat message {i} from {client.client_id}"
                )
                chat_result = await client.send_and_wait_response(chat_msg, timeout=2.0)
                results.append(chat_result)
        
        return results
    
    @staticmethod
    async def comprehensive_test(client: MockWebSocketClient) -> List[TestResult]:
        """综合功能测试"""
        user_id = f"test_user_{client.client_id}"
        player_id = f"test_player_{client.client_id}"
        results = []
        
        # 1. 登录
        login_msg = MessageBuilder.create_login_message(user_id, player_id)
        login_result = await client.send_and_wait_response(login_msg)
        results.append(login_result)
        
        if not login_result.success:
            return results
        
        # 2. 查询玩家信息
        info_msg = MessageBuilder.create_player_info_query(player_id)
        info_result = await client.send_and_wait_response(info_msg)
        results.append(info_result)
        
        # 3. 发送聊天消息
        chat_msg = MessageBuilder.create_chat_message(player_id, "Hello from comprehensive test!")
        chat_result = await client.send_and_wait_response(chat_msg, timeout=2.0)
        results.append(chat_result)
        
        # 4. 发起战斗
        battle_msg = MessageBuilder.create_battle_message(player_id, "npc_001")
        battle_result = await client.send_and_wait_response(battle_msg, timeout=10.0)
        results.append(battle_result)
        
        # 5. 心跳
        heartbeat_msg = MessageBuilder.create_heartbeat_message(player_id)
        heartbeat_result = await client.send_and_wait_response(heartbeat_msg, timeout=2.0)
        results.append(heartbeat_result)
        
        return results
    
    @staticmethod
    async def stress_test(client: MockWebSocketClient) -> List[TestResult]:
        """压力测试场景"""
        user_id = f"stress_user_{client.client_id}"
        player_id = f"stress_player_{client.client_id}"
        results = []
        
        # 登录
        login_msg = MessageBuilder.create_login_message(user_id, player_id)
        login_result = await client.send_and_wait_response(login_msg)
        results.append(login_result)
        
        if login_result.success:
            # 高频发送消息
            for i in range(50):
                if i % 10 == 0:
                    # 每10条消息查询一次玩家信息
                    msg = MessageBuilder.create_player_info_query(player_id)
                    timeout = 3.0
                else:
                    # 其他为聊天消息
                    msg = MessageBuilder.create_chat_message(player_id, f"Stress message {i}")
                    timeout = 1.0
                
                result = await client.send_and_wait_response(msg, timeout=timeout)
                results.append(result)
                
                # 短暂延迟防止过载
                await asyncio.sleep(0.01)
        
        return results


def print_batch_stats(stats: BatchTestStats):
    """打印批量测试统计信息"""
    print("\n" + "="*60)
    print("BATCH TEST RESULTS")
    print("="*60)
    
    print(f"Total Clients: {stats.total_clients}")
    print(f"Successful Clients: {stats.successful_clients}")
    print(f"Failed Clients: {stats.failed_clients}")
    print(f"Client Success Rate: {(stats.successful_clients/stats.total_clients)*100:.2f}%")
    
    print(f"\nTotal Messages: {stats.total_messages}")
    print(f"Successful Messages: {stats.successful_messages}")
    print(f"Failed Messages: {stats.failed_messages}")
    print(f"Message Success Rate: {(100-stats.error_rate):.2f}%")
    
    print(f"\nResponse Time Stats:")
    print(f"Average: {stats.avg_response_time*1000:.2f}ms")
    print(f"Min: {stats.min_response_time*1000:.2f}ms")
    print(f"Max: {stats.max_response_time*1000:.2f}ms")
    
    print(f"\nThroughput:")
    print(f"Messages/Second: {stats.messages_per_second:.2f}")
    print(f"Clients/Second: {stats.clients_per_second:.2f}")
    print(f"Total Duration: {stats.total_duration:.2f}s")
    
    # 错误详情
    if stats.failed_messages > 0:
        print(f"\nError Details:")
        error_types = {}
        for result in stats.detailed_results:
            if not result.success and result.error_message:
                error_types[result.error_message] = error_types.get(result.error_message, 0) + 1
        
        for error, count in error_types.items():
            print(f"  {error}: {count}")


# 示例使用
async def main():
    """主函数示例"""
    print("Mock WebSocket Client Test Suite")
    
    # 创建批量测试运行器
    runner = BatchTestRunner(server_url="ws://localhost:8000/ws", max_concurrent=50)
    
    # 运行简单登录测试
    print("\n1. Running simple login test with 10 clients...")
    stats = await runner.run_batch_test(10, TestScenarios.simple_login_test)
    print_batch_stats(stats)
    
    # 运行聊天洪水测试
    print("\n2. Running chat flood test with 5 clients...")
    stats = await runner.run_batch_test(5, TestScenarios.chat_flood_test)
    print_batch_stats(stats)
    
    # 运行综合测试
    print("\n3. Running comprehensive test with 3 clients...")
    stats = await runner.run_batch_test(3, TestScenarios.comprehensive_test)
    print_batch_stats(stats)


if __name__ == "__main__":
    # 运行示例测试
    asyncio.run(main())