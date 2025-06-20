# 骑士英雄游戏服务器 Knight Hero Game Server

## 项目概述

骑士英雄游戏服务器是一个基于Python 3.12的高性能多人在线游戏服务器架构。采用微服务设计，支持网关、逻辑、聊天、战斗等多个独立服务模块。

## 技术栈

- **Python**: 3.12.6
- **依赖管理**: Poetry
- **异步框架**: FastAPI + uvloop
- **WebSocket**: websockets
- **数据库**: MongoDB (motor), Redis
- **通信协议**: gRPC, HTTP, WebSocket
- **数据序列化**: Protobuf, orjson
- **进程管理**: supervisor
- **测试框架**: pytest + pytest-asyncio

## 项目结构

```
game_server/
├── pyproject.toml          # Poetry项目配置文件
├── poetry.lock             # 依赖锁定文件
├── README.md               # 项目说明文档
├── .gitignore              # Git忽略文件配置
├── .env.example            # 环境变量示例文件
├── common/                 # 公共模块
│   ├── __init__.py
│   ├── protocol/           # 通信协议定义
│   ├── database/           # 数据库相关组件
│   ├── grpc/               # gRPC服务定义
│   ├── logger/             # 日志组件
│   └── config/             # 配置管理
├── services/               # 服务模块
│   ├── __init__.py
│   ├── gateway/            # 网关服务
│   ├── logic/              # 游戏逻辑服务
│   ├── chat/               # 聊天服务
│   └── fight/              # 战斗服务
├── launcher/               # 启动器脚本
├── json/                   # JSON配置文件
├── doc/                    # 文档目录
└── test/                   # 测试用例
```

## 快速开始

### 环境要求

- Python 3.12.6+
- Poetry (依赖管理工具)
- MongoDB
- Redis

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/mrkingu/knight_hero_server.git
   cd knight_hero_server
   ```

2. **安装依赖**
   ```bash
   poetry install
   ```

3. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入实际的配置信息
   ```

4. **启动服务**
   ```bash
   poetry shell
   # 启动相应的服务
   ```

### 开发环境

1. **激活虚拟环境**
   ```bash
   poetry shell
   ```

2. **运行测试**
   ```bash
   pytest
   ```

3. **代码格式化**
   ```bash
   black .
   isort .
   ```

## 服务架构

### 网关服务 (Gateway)
- 负责客户端连接管理
- WebSocket通信处理
- 请求路由分发
- 身份验证和授权

### 游戏逻辑服务 (Logic)
- 核心游戏逻辑处理
- 玩家数据管理
- 游戏状态同步
- 业务规则实现

### 聊天服务 (Chat)
- 实时聊天功能
- 频道管理
- 消息过滤和审核
- 聊天记录存储

### 战斗服务 (Fight)
- 战斗逻辑计算
- 技能效果处理
- 伤害计算
- 战斗结果统计

## 开发规范

- **代码风格**: 遵循PEP 8规范
- **类型注解**: 使用Type Hints进行类型标注
- **注释**: 所有代码必须包含详细的中文注释
- **测试**: 编写完整的单元测试和集成测试
- **文档**: 及时更新API文档和使用说明

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 作者

- **lx** - 初始开发 - 2025-06-18

## 更新日志

### v0.1.0 (2025-06-18)
- 初始项目结构搭建
- 基础服务架构设计
- 核心依赖配置完成