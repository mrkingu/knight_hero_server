# Launcher启动器使用指南

## 概述

Launcher系统是一个完整的游戏服务器编排和一键启动解决方案，提供了：

- YAML配置文件管理
- Supervisor进程管理
- Nginx负载均衡和WebSocket支持
- 全面的健康检查系统
- 自动配置生成
- 优雅的启动和关闭

## 快速开始

### 1. 配置文件

编辑 `launcher/config.yaml`:

```yaml
environment: development

services:
  gateway:
    instances: 2
    start_port: 8000
    workers: 4
    env:
      MAX_CONNECTIONS: 10000
      
  logic:
    instances: 2  
    start_port: 9000
    workers: 4
    
  chat:
    instances: 1
    start_port: 9100
    workers: 2
    
  fight:
    instances: 2
    start_port: 9200
    workers: 2

redis:
  mode: single
  host: localhost
  port: 6379
  
mongodb:
  uri: mongodb://localhost:27017/game
  
nginx:
  workers: 4
  port: 80
```

### 2. 启动单个服务

```bash
# 启动Gateway服务
poetry run python launcher/server.py gateway --port 8000

# 启动Logic服务
poetry run python launcher/server.py logic --port 9000 --debug

# 启动Chat服务
poetry run python launcher/server.py chat --port 9100
```

### 3. 一键启动所有服务

```bash
# 使用默认配置启动所有服务
poetry run python launcher/server.py all

# 使用自定义配置文件
poetry run python launcher/server.py all --config custom_config.yaml
```

### 4. 编程接口使用

```python
import asyncio
from launcher.launcher import Launcher

async def main():
    # 创建启动器实例
    launcher = Launcher("launcher/config.yaml")
    
    # 初始化
    if not await launcher.initialize():
        print("初始化失败")
        return
    
    # 启动所有服务
    success = await launcher.start_all()
    if not success:
        print("启动失败")
        return
    
    # 等待关闭信号
    await launcher.wait_for_shutdown()
    
    # 停止所有服务
    await launcher.stop_all()

if __name__ == "__main__":
    asyncio.run(main())
```

## 系统组件

### Supervisor配置生成器 (supervisor_gen.py)

自动生成supervisor配置文件，包括：

- 主配置文件 `supervisord.conf`
- 各服务的进程配置
- 进程组管理
- 日志配置
- 自动重启策略

```python
from launcher.supervisor_gen import SupervisorConfigGenerator, SupervisorConfig

# 创建配置生成器
supervisor_config = SupervisorConfig(
    project_dir="/opt/game_server",
    environment="production"
)
generator = SupervisorConfigGenerator(config, supervisor_config)

# 生成并保存配置
generator.save_configs("/etc/supervisor")
```

### Nginx配置生成器 (nginx_gen.py)

自动生成nginx负载均衡配置，支持：

- 上游服务器配置
- WebSocket支持
- 健康检查
- 负载均衡策略
- 安全配置

```python
from launcher.nginx_gen import NginxConfigGenerator, NginxGlobalConfig

# 创建配置生成器
nginx_config = NginxGlobalConfig(worker_processes=4)
generator = NginxConfigGenerator(config, nginx_config)

# 生成并保存配置
generator.save_configs("/etc/nginx")
```

### 健康检查系统 (health_check.py)

提供全面的健康检查功能：

- HTTP健康检查
- gRPC连接检查
- Redis连接检查
- MongoDB连接检查

```python
from launcher.health_check import HealthCheckManager

# 创建健康检查管理器
health_manager = HealthCheckManager()

# 检查所有服务健康状态
results = await health_manager.check_service_health(config)
summary = health_manager.get_health_summary(results)

print(f"健康服务: {summary['healthy_services']}/{summary['total_services']}")
```

## 部署模式

### 开发环境

```yaml
environment: development
services:
  gateway:
    instances: 1
    start_port: 8000
    workers: 2
```

### 生产环境

```yaml
environment: production
services:
  gateway:
    instances: 4
    start_port: 8000
    workers: 8
    env:
      MAX_CONNECTIONS: 50000
      REDIS_POOL_SIZE: 20
```

## 监控和管理

### 查看服务状态

```bash
# Supervisor状态
sudo supervisorctl status

# Nginx状态
sudo nginx -s reload
curl http://localhost:8080/nginx_status
```

### 重启单个服务

```python
# 重启logic服务
await launcher.restart_service("logic")
```

### 获取系统状态

```python
# 获取完整系统状态
status = await launcher.get_status()
print(f"系统运行状态: {status['launcher']['running']}")
print(f"健康检查: {status['health']['health_percentage']:.1f}%")
```

## 故障排除

### 常见问题

1. **端口被占用**
   - 检查端口使用: `netstat -tlnp | grep :8000`
   - 修改配置文件中的端口号

2. **权限不足**
   - 使用sudo运行: `sudo poetry run python launcher/server.py all`
   - 检查日志目录权限: `/var/log/game`

3. **配置验证失败**
   - 检查YAML语法
   - 验证端口范围
   - 确认项目路径正确

### 日志查看

```bash
# Supervisor日志
tail -f /var/log/game/supervisord.log
tail -f /var/log/game/gateway_1_out.log

# Nginx日志
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

## 测试

运行测试套件：

```bash
# 运行启动器测试
poetry run python -m pytest test/test_launcher.py -v

# 运行所有测试
poetry run python -m pytest test/ -v
```

## 性能优化

### 系统级优化

- 使用uvloop事件循环
- 调整worker进程数量
- 优化数据库连接池
- 配置合适的超时时间

### 监控指标

- 响应时间
- 连接数
- 内存使用
- CPU利用率
- 错误率

通过Launcher系统，您可以轻松管理复杂的游戏服务器部署，实现高可用、高性能的服务编排。