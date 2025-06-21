"""
Locust压力测试
Locust Load Testing

作者: lx
日期: 2025-06-18
描述: 使用Locust进行压力测试，模拟10K用户，各种业务场景，性能报告生成
"""

import json
import time
import random
import uuid
from typing import Dict, Any, List
import websocket
import threading
from locust import HttpUser, task, between, events
from locust.exception import StopUser
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GameWebSocketClient:
    """游戏WebSocket客户端"""
    
    def __init__(self, host: str = "localhost", port: int = 8000, user_id: str = None):
        self.host = host
        self.port = port
        self.user_id = user_id or f"user_{uuid.uuid4().hex[:8]}"
        self.player_id = f"player_{self.user_id}"
        self.ws = None
        self.connected = False
        self.message_queue = []
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "connection_time": None,
            "errors": 0
        }
        
    def connect(self) -> bool:
        """连接WebSocket"""
        try:
            url = f"ws://{self.host}:{self.port}/ws"
            self.ws = websocket.WebSocket()
            start_time = time.time()
            self.ws.connect(url)
            self.stats["connection_time"] = time.time() - start_time
            self.connected = True
            logger.info(f"User {self.user_id} connected")
            return True
        except Exception as e:
            logger.error(f"Connection failed for {self.user_id}: {e}")
            self.stats["errors"] += 1
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.ws and self.connected:
            try:
                self.ws.close()
                self.connected = False
                logger.info(f"User {self.user_id} disconnected")
            except Exception as e:
                logger.error(f"Disconnect error for {self.user_id}: {e}")
    
    def send_message(self, message: Dict[str, Any]) -> bool:
        """发送消息"""
        if not self.connected or not self.ws:
            return False
            
        try:
            message_data = json.dumps(message)
            self.ws.send(message_data)
            self.stats["messages_sent"] += 1
            return True
        except Exception as e:
            logger.error(f"Send message error for {self.user_id}: {e}")
            self.stats["errors"] += 1
            return False
    
    def receive_message(self, timeout: float = 1.0) -> Dict[str, Any]:
        """接收消息"""
        if not self.connected or not self.ws:
            return None
            
        try:
            self.ws.settimeout(timeout)
            data = self.ws.recv()
            message = json.loads(data)
            self.stats["messages_received"] += 1
            return message
        except websocket.WebSocketTimeoutException:
            return None
        except Exception as e:
            logger.error(f"Receive message error for {self.user_id}: {e}")
            self.stats["errors"] += 1
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()


class GameUser(HttpUser):
    """游戏用户模拟类"""
    
    wait_time = between(1, 3)  # 用户操作间隔1-3秒
    
    def on_start(self):
        """用户启动时的初始化"""
        self.user_id = f"load_user_{uuid.uuid4().hex[:8]}"
        self.player_id = f"load_player_{self.user_id}"
        self.device_id = f"device_{uuid.uuid4().hex[:8]}"
        
        # 初始化WebSocket客户端
        self.ws_client = GameWebSocketClient(
            host=self.host.split("://")[1].split(":")[0] if "://" in self.host else self.host,
            port=8000,  # WebSocket端口
            user_id=self.user_id
        )
        
        # 连接WebSocket
        if not self.ws_client.connect():
            logger.error(f"Failed to connect WebSocket for {self.user_id}")
            raise StopUser()
        
        # 执行登录
        self.login()
        
        # 初始化玩家状态
        self.player_state = {
            "level": random.randint(1, 50),
            "exp": random.randint(0, 10000),
            "gold": random.randint(100, 10000),
            "hp": 100,
            "mp": 50,
            "location": {
                "x": random.uniform(0, 1000),
                "y": random.uniform(0, 1000),
                "z": 0
            }
        }
    
    def on_stop(self):
        """用户停止时的清理"""
        self.logout()
        if self.ws_client:
            self.ws_client.disconnect()
    
    def login(self):
        """登录操作"""
        login_message = {
            "msg_id": 1001,
            "player_id": self.player_id,
            "data": {
                "user_id": self.user_id,
                "device_id": self.device_id,
                "version": "1.0.0",
                "timestamp": time.time()
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(login_message)
        
        if success:
            # 等待登录响应
            response = self.ws_client.receive_message(timeout=5.0)
            response_time = (time.time() - start_time) * 1000
            
            if response and response.get("code") == 0:
                events.request_success.fire(
                    request_type="WebSocket",
                    name="login",
                    response_time=response_time,
                    response_length=len(json.dumps(response))
                )
                logger.info(f"User {self.user_id} logged in successfully")
            else:
                events.request_failure.fire(
                    request_type="WebSocket",
                    name="login",
                    response_time=response_time,
                    response_length=0,
                    exception="Login failed"
                )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="login",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send login message"
            )
    
    def logout(self):
        """登出操作"""
        logout_message = {
            "msg_id": 1003,
            "player_id": self.player_id,
            "data": {},
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(logout_message)
        
        if success:
            response = self.ws_client.receive_message(timeout=3.0)
            response_time = (time.time() - start_time) * 1000
            
            if response:
                events.request_success.fire(
                    request_type="WebSocket",
                    name="logout",
                    response_time=response_time,
                    response_length=len(json.dumps(response))
                )
            else:
                events.request_failure.fire(
                    request_type="WebSocket",
                    name="logout",
                    response_time=response_time,
                    response_length=0,
                    exception="No logout response"
                )
    
    @task(3)
    def send_chat_message(self):
        """发送聊天消息 - 高频操作"""
        chat_messages = [
            "Hello everyone!",
            "How is everyone doing?",
            "Anyone want to team up?",
            "Great game!",
            "Looking for guild members",
            "Trading rare items",
            "Help me with this quest",
            "GG WP!",
            "Let's go!",
            "Amazing battle!"
        ]
        
        chat_message = {
            "msg_id": 2001,
            "player_id": self.player_id,
            "data": {
                "content": random.choice(chat_messages),
                "channel": random.choice(["world", "guild", "team"]),
                "timestamp": time.time()
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(chat_message)
        
        if success:
            # 聊天消息通常不需要等待响应
            response_time = (time.time() - start_time) * 1000
            events.request_success.fire(
                request_type="WebSocket",
                name="chat_message",
                response_time=response_time,
                response_length=len(json.dumps(chat_message))
            )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="chat_message",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send chat message"
            )
    
    @task(2)
    def query_player_info(self):
        """查询玩家信息 - 中频操作"""
        query_message = {
            "msg_id": 1002,
            "player_id": self.player_id,
            "data": {
                "query_type": "basic_info",
                "include_stats": True,
                "include_inventory": random.choice([True, False])
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(query_message)
        
        if success:
            response = self.ws_client.receive_message(timeout=3.0)
            response_time = (time.time() - start_time) * 1000
            
            if response and response.get("code") == 0:
                events.request_success.fire(
                    request_type="WebSocket",
                    name="query_player_info",
                    response_time=response_time,
                    response_length=len(json.dumps(response))
                )
                
                # 更新本地玩家状态
                if "data" in response:
                    self.player_state.update(response["data"])
            else:
                events.request_failure.fire(
                    request_type="WebSocket",
                    name="query_player_info",
                    response_time=response_time,
                    response_length=0,
                    exception="Query failed or timeout"
                )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="query_player_info",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send query message"
            )
    
    @task(1)
    def start_battle(self):
        """发起战斗 - 低频重操作"""
        battle_types = ["pve", "pvp", "boss", "dungeon"]
        targets = ["npc_001", "npc_002", "boss_001", "player_bot_001"]
        
        battle_message = {
            "msg_id": 3001,
            "player_id": self.player_id,
            "data": {
                "battle_type": random.choice(battle_types),
                "target_id": random.choice(targets),
                "location": self.player_state["location"],
                "equipment": {
                    "weapon": "sword_001",
                    "armor": "armor_001",
                    "accessories": ["ring_001", "amulet_001"]
                }
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(battle_message)
        
        if success:
            response = self.ws_client.receive_message(timeout=10.0)  # 战斗可能需要更长时间
            response_time = (time.time() - start_time) * 1000
            
            if response and response.get("code") == 0:
                events.request_success.fire(
                    request_type="WebSocket",
                    name="start_battle",
                    response_time=response_time,
                    response_length=len(json.dumps(response))
                )
                
                # 模拟战斗结果更新玩家状态
                if response.get("data", {}).get("result") == "victory":
                    self.player_state["exp"] += random.randint(100, 500)
                    self.player_state["gold"] += random.randint(50, 200)
            else:
                events.request_failure.fire(
                    request_type="WebSocket",
                    name="start_battle",
                    response_time=response_time,
                    response_length=0,
                    exception="Battle failed or timeout"
                )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="start_battle",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send battle message"
            )
    
    @task(1)
    def move_player(self):
        """移动玩家位置"""
        # 随机移动
        new_location = {
            "x": self.player_state["location"]["x"] + random.uniform(-10, 10),
            "y": self.player_state["location"]["y"] + random.uniform(-10, 10),
            "z": 0
        }
        
        move_message = {
            "msg_id": 4001,
            "player_id": self.player_id,
            "data": {
                "from_location": self.player_state["location"],
                "to_location": new_location,
                "movement_type": "walk"
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(move_message)
        
        if success:
            # 移动消息通常是fire-and-forget
            response_time = (time.time() - start_time) * 1000
            events.request_success.fire(
                request_type="WebSocket",
                name="move_player",
                response_time=response_time,
                response_length=len(json.dumps(move_message))
            )
            
            # 更新本地位置
            self.player_state["location"] = new_location
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="move_player",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send move message"
            )
    
    @task(1)
    def use_item(self):
        """使用道具"""
        items = [
            {"id": 1001, "name": "小血瓶", "effect": "heal_hp"},
            {"id": 1002, "name": "魔法卷轴", "effect": "restore_mp"},
            {"id": 1003, "name": "经验药水", "effect": "boost_exp"},
            {"id": 1004, "name": "速度药水", "effect": "boost_speed"}
        ]
        
        item = random.choice(items)
        
        use_item_message = {
            "msg_id": 5001,
            "player_id": self.player_id,
            "data": {
                "item_id": item["id"],
                "item_name": item["name"],
                "quantity": 1,
                "target": "self"
            },
            "timestamp": time.time(),
            "sequence": str(uuid.uuid4())
        }
        
        start_time = time.time()
        success = self.ws_client.send_message(use_item_message)
        
        if success:
            response = self.ws_client.receive_message(timeout=5.0)
            response_time = (time.time() - start_time) * 1000
            
            if response and response.get("code") == 0:
                events.request_success.fire(
                    request_type="WebSocket",
                    name="use_item",
                    response_time=response_time,
                    response_length=len(json.dumps(response))
                )
                
                # 模拟道具效果
                if item["effect"] == "heal_hp":
                    self.player_state["hp"] = min(100, self.player_state["hp"] + 20)
                elif item["effect"] == "restore_mp":
                    self.player_state["mp"] = min(100, self.player_state["mp"] + 15)
            else:
                events.request_failure.fire(
                    request_type="WebSocket",
                    name="use_item",
                    response_time=response_time,
                    response_length=0,
                    exception="Use item failed"
                )
        else:
            events.request_failure.fire(
                request_type="WebSocket",
                name="use_item",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception="Failed to send use item message"
            )


# 自定义事件处理器，用于收集额外的统计信息
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """测试开始时的初始化"""
    logger.info("Load test starting...")
    environment.stats.total_websocket_connections = 0
    environment.stats.total_websocket_errors = 0


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时的统计"""
    logger.info("Load test completed")
    
    # 生成详细报告
    stats = environment.stats
    
    print("\n" + "="*60)
    print("LOAD TEST SUMMARY REPORT")
    print("="*60)
    
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Min Response Time: {stats.total.min_response_time:.2f}ms")
    print(f"Max Response Time: {stats.total.max_response_time:.2f}ms")
    print(f"RPS (Requests Per Second): {stats.total.current_rps:.2f}")
    
    if stats.total.num_requests > 0:
        failure_rate = (stats.total.num_failures / stats.total.num_requests) * 100
        print(f"Failure Rate: {failure_rate:.2f}%")
    
    print("\nDETAILED STATS BY REQUEST TYPE:")
    print("-" * 40)
    for name, entry in stats.entries.items():
        if entry.num_requests > 0:
            print(f"{name}:")
            print(f"  Requests: {entry.num_requests}")
            print(f"  Failures: {entry.num_failures}")
            print(f"  Avg Response Time: {entry.avg_response_time:.2f}ms")
            print(f"  RPS: {entry.current_rps:.2f}")
            print()


# 如果直接运行此文件，可以用于本地测试
if __name__ == "__main__":
    import os
    
    # 设置环境变量进行本地测试
    os.environ["LOCUST_HOST"] = "http://localhost:8000"
    
    print("Local WebSocket client test")
    
    # 创建测试客户端
    client = GameWebSocketClient(host="localhost", port=8000)
    
    if client.connect():
        print("Connected successfully")
        
        # 发送测试消息
        test_message = {
            "msg_id": 1001,
            "player_id": "test_player",
            "data": {"test": True},
            "timestamp": time.time()
        }
        
        success = client.send_message(test_message)
        print(f"Message sent: {success}")
        
        client.disconnect()
        print("Disconnected")
        
        stats = client.get_stats()
        print(f"Final stats: {stats}")
    else:
        print("Failed to connect")