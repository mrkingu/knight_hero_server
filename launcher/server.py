#!/usr/bin/env python3
"""
游戏服务器启动器
Game Server Launcher

作者: lx
日期: 2025-06-18
描述: 游戏服务器主启动入口，支持启动不同的服务模块
"""

import asyncio
import argparse
import sys
from typing import Optional

try:
    import uvloop
    # 使用uvloop替代默认事件循环以获得更好的性能
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    print("警告: uvloop未安装，使用默认事件循环")


async def start_single_service(service: str, host: str, port: int, debug: bool) -> None:
    """
    启动单个服务
    
    Args:
        service: 服务名称
        host: 主机地址
        port: 端口号
        debug: 是否调试模式
    """
    try:
        if service == "gateway":
            # 启动Gateway服务
            from services.gateway.main import startup
            app = await startup()
            
            import uvicorn
            config = uvicorn.Config(
                app=app,
                host=host,
                port=port,
                loop="uvloop",
                log_level="debug" if debug else "info",
                access_log=True
            )
            server = uvicorn.Server(config)
            await server.serve()
            
        elif service == "logic":
            # 启动Logic服务
            from services.logic.main import LogicService
            logic_service = LogicService()
            await logic_service.start(host=host, port=port, debug=debug)
            
        elif service == "chat":
            # 启动Chat服务
            from services.chat.main import ChatService
            chat_service = ChatService()
            await chat_service.start(host=host, port=port, debug=debug)
            
        elif service == "fight":
            # 启动Fight服务
            from services.fight.main import FightService
            fight_service = FightService()
            await fight_service.start(host=host, port=port, debug=debug)
            
    except Exception as e:
        print(f"启动 {service} 服务失败: {e}")
        sys.exit(1)


async def start_all_services_with_launcher(config_file: str = "launcher/config.yaml") -> None:
    """
    使用Launcher启动所有服务
    
    Args:
        config_file: 配置文件路径
    """
    try:
        from .launcher import Launcher
        
        launcher = Launcher(config_file)
        
        # 初始化启动器
        if not await launcher.initialize():
            print("启动器初始化失败")
            sys.exit(1)
        
        # 启动所有服务
        success = await launcher.start_all()
        if not success:
            print("服务启动失败")
            sys.exit(1)
        
        print("所有服务启动成功!")
        
        try:
            # 等待关闭信号
            await launcher.wait_for_shutdown()
        finally:
            # 停止所有服务
            await launcher.stop_all()
            
    except KeyboardInterrupt:
        print("\\n接收到中断信号，正在关闭...")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)


def main() -> None:
    """
    主入口函数
    Main entry function
    """
    parser = argparse.ArgumentParser(description="骑士英雄游戏服务器启动器")
    parser.add_argument(
        "service",
        choices=["gateway", "logic", "chat", "fight", "all"],
        help="要启动的服务类型"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="服务器主机地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务器端口 (默认: 8000)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    parser.add_argument(
        "--config",
        default="launcher/config.yaml",
        help="配置文件路径 (默认: launcher/config.yaml)"
    )

    args = parser.parse_args()

    print(f"正在启动 {args.service} 服务...")
    print(f"主机: {args.host}, 端口: {args.port}")
    print(f"调试模式: {'开启' if args.debug else '关闭'}")

    async def run_service():
        if args.service == "all":
            print("使用Launcher启动所有服务...")
            await start_all_services_with_launcher(args.config)
        else:
            print(f"启动 {args.service} 服务...")
            await start_single_service(args.service, args.host, args.port, args.debug)

    # 运行服务
    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        print("\\n服务已停止")
    except Exception as e:
        print(f"运行错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()