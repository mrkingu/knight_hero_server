"""
测试框架配置
Test Framework Configuration

作者: lx
日期: 2025-06-18
描述: 测试框架的各种配置示例和最佳实践
"""

import os
from pathlib import Path

# 测试环境配置
TEST_FRAMEWORK_CONFIG = {
    # 服务器配置
    "server": {
        "host": "localhost",
        "port": 8000,
        "websocket_port": 8000,
        "websocket_path": "/ws"
    },
    
    # 数据库配置
    "database": {
        "mongodb_url": "mongodb://localhost:27017/test_db",
        "redis_url": "redis://localhost:6379/1",
        "use_mock": True  # 在测试中使用Mock数据库
    },
    
    # 测试数据配置
    "test_data": {
        "user_count": 1000,
        "player_count": 1000,
        "message_count": 10000,
        "test_duration": 300  # 5分钟
    },
    
    # 性能基准
    "performance": {
        "max_response_time_ms": 100,
        "min_throughput_msg_sec": 1000,
        "max_error_rate_percent": 1.0,
        "max_memory_mb": 512,
        "max_cpu_percent": 80.0
    },
    
    # 压力测试配置
    "load_test": {
        "max_users": 10000,
        "spawn_rate": 100,
        "test_duration": 300,
        "scenarios": {
            "login_only": {"weight": 10},
            "chat_heavy": {"weight": 30},
            "battle_heavy": {"weight": 20},
            "mixed_operations": {"weight": 40}
        }
    },
    
    # 测试超时配置
    "timeouts": {
        "connection_timeout": 10.0,
        "message_timeout": 5.0,
        "test_timeout": 30.0,
        "cleanup_timeout": 5.0
    }
}

# pytest配置
PYTEST_CONFIG = {
    "asyncio_mode": "auto",
    "timeout": 30,
    "markers": [
        "unit: Unit tests",
        "integration: Integration tests", 
        "load: Load tests",
        "slow: Slow running tests",
        "performance: Performance tests"
    ]
}

# Locust配置
LOCUST_CONFIG = {
    "host": f"http://{TEST_FRAMEWORK_CONFIG['server']['host']}:{TEST_FRAMEWORK_CONFIG['server']['port']}",
    "users": TEST_FRAMEWORK_CONFIG["load_test"]["max_users"],
    "spawn_rate": TEST_FRAMEWORK_CONFIG["load_test"]["spawn_rate"],
    "run_time": f"{TEST_FRAMEWORK_CONFIG['load_test']['test_duration']}s",
    "headless": True,
    "html": "reports/locust_report.html",
    "csv": "reports/locust_stats"
}

# 环境变量设置
def setup_test_environment():
    """设置测试环境变量"""
    env_vars = {
        "TEST_MODE": "true",
        "LOG_LEVEL": "INFO",
        "DATABASE_URL": TEST_FRAMEWORK_CONFIG["database"]["mongodb_url"],
        "REDIS_URL": TEST_FRAMEWORK_CONFIG["database"]["redis_url"],
        "SERVER_HOST": TEST_FRAMEWORK_CONFIG["server"]["host"],
        "SERVER_PORT": str(TEST_FRAMEWORK_CONFIG["server"]["port"]),
        "USE_MOCK_DB": str(TEST_FRAMEWORK_CONFIG["database"]["use_mock"]).lower()
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value

# 测试数据路径
TEST_PATHS = {
    "data": Path(__file__).parent / "data",
    "fixtures": Path(__file__).parent / "fixtures", 
    "reports": Path(__file__).parent / "reports",
    "logs": Path(__file__).parent / "logs"
}

# 创建测试目录
def create_test_directories():
    """创建必要的测试目录"""
    for path in TEST_PATHS.values():
        path.mkdir(exist_ok=True)

# 测试场景配置
TEST_SCENARIOS = {
    "smoke_test": {
        "description": "冒烟测试 - 快速验证基本功能",
        "duration": 60,
        "users": 10,
        "operations": ["login", "logout"]
    },
    
    "functionality_test": {
        "description": "功能测试 - 验证所有功能模块",
        "duration": 300,
        "users": 100,
        "operations": ["login", "chat", "battle", "query", "logout"]
    },
    
    "performance_test": {
        "description": "性能测试 - 验证性能指标",
        "duration": 600,
        "users": 1000,
        "operations": ["login", "chat", "query", "logout"]
    },
    
    "stress_test": {
        "description": "压力测试 - 验证系统极限",
        "duration": 1800,
        "users": 10000,
        "operations": ["login", "chat", "battle", "query", "move", "logout"]
    },
    
    "endurance_test": {
        "description": "耐久测试 - 长期稳定性验证",
        "duration": 7200,  # 2小时
        "users": 5000,
        "operations": ["login", "chat", "query", "heartbeat", "logout"]
    }
}

# 测试报告配置
REPORT_CONFIG = {
    "output_dir": "reports",
    "formats": ["html", "json", "csv"],
    "include_graphs": True,
    "include_raw_data": True,
    "auto_open": False
}

if __name__ == "__main__":
    # 初始化测试环境
    setup_test_environment()
    create_test_directories()
    
    print("测试配置已初始化")
    print(f"服务器地址: {TEST_FRAMEWORK_CONFIG['server']['host']}:{TEST_FRAMEWORK_CONFIG['server']['port']}")
    print(f"最大用户数: {TEST_FRAMEWORK_CONFIG['load_test']['max_users']}")
    print(f"测试路径: {TEST_PATHS}")