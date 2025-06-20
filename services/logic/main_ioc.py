"""
Logic服务启动入口 - IoC版本
Logic Service Main Entry with IoC Support

作者: mrkingu
日期: 2025-06-20
描述: 自动扫描并装载所有服务，支持依赖注入和生命周期管理
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from common.ioc import ServiceContainer, ServiceScanner
from common.ioc.exceptions import ContainerException

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogicServer:
    """
    Logic服务器
    
    负责启动和管理所有Logic服务组件
    """
    
    def __init__(self):
        self.container = ServiceContainer()
        self.scanner = ServiceScanner()
        self._shutdown_event = asyncio.Event()
        self._running = False
    
    async def start(self) -> None:
        """启动服务"""
        try:
            logger.info("Starting Logic Server...")
            
            # 1. 扫描并加载所有服务
            scan_paths = [
                "services/logic/services",
                "services/logic/handlers", 
                "services/logic/repositories"
            ]
            
            logger.info(f"Scanning for services in: {scan_paths}")
            
            # 2. 初始化容器
            await self.container.initialize(scan_paths)
            
            # 3. 获取服务统计信息
            container_info = self.container.get_container_info()
            logger.info(f"Container initialized with {container_info['total_services']} services")
            logger.info(f"Active instances: {container_info['active_instances']}")
            logger.info(f"Initialization order: {container_info['initialization_order']}")
            
            # 4. 启动HTTP/gRPC服务器（模拟）
            await self._start_grpc_server()
            
            # 5. 设置信号处理
            self._setup_signal_handlers()
            
            self._running = True
            logger.info("Logic Server started successfully!")
            
            # 6. 等待退出信号
            await self._wait_for_shutdown()
            
        except ContainerException as e:
            logger.error(f"Failed to start Logic Server: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error starting Logic Server: {e}")
            sys.exit(1)
    
    async def _start_grpc_server(self) -> None:
        """启动gRPC服务器（模拟实现）"""
        try:
            # 获取所有Handler
            handlers = self.container.get_services_by_type("service")
            handler_list = [name for name in handlers.keys() if "Handler" in name]
            
            logger.info(f"Registered handlers: {handler_list}")
            
            # 这里应该注册到实际的gRPC服务器
            # grpc_server = create_grpc_server()
            # for handler_name, handler_instance in handlers.items():
            #     if "Handler" in handler_name:
            #         register_handler(grpc_server, handler_instance)
            # 
            # await grpc_server.start()
            
            logger.info("gRPC server started (simulated)")
            
        except Exception as e:
            logger.error(f"Failed to start gRPC server: {e}")
            raise
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
    
    async def shutdown(self) -> None:
        """关闭服务"""
        if not self._running:
            return
        
        logger.info("Shutting down Logic Server...")
        self._running = False
        
        try:
            # 关闭容器
            await self.container.shutdown()
            
            # 设置关闭事件
            self._shutdown_event.set()
            
            logger.info("Logic Server shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    async def health_check(self) -> dict:
        """健康检查"""
        container_info = self.container.get_container_info()
        
        # 检查所有服务的健康状态
        service_health = {}
        for service_name in container_info["services"]:
            try:
                if self.container.has_service(service_name):
                    service = self.container.get_service(service_name)
                    if hasattr(service, 'health_check'):
                        service_health[service_name] = await service.health_check()
                    else:
                        service_health[service_name] = {"status": "unknown"}
                else:
                    service_health[service_name] = {"status": "not_initialized"}
            except Exception as e:
                service_health[service_name] = {"status": "error", "error": str(e)}
        
        return {
            "server_status": "running" if self._running else "stopped",
            "container": container_info,
            "services": service_health
        }


async def main():
    """主入口函数"""
    server = LogicServer()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await server.shutdown()


if __name__ == "__main__":
    # 简单的命令行参数处理
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "test":
            # 测试模式 - 只初始化服务但不启动服务器
            async def test_mode():
                server = LogicServer()
                try:
                    logger.info("Running in test mode...")
                    await server.container.initialize([
                        "services/logic/services",
                        "services/logic/handlers",
                        "services/logic/repositories"
                    ])
                    
                    # 显示容器信息
                    info = await server.health_check()
                    logger.info(f"Test completed successfully. Container status: {info}")
                    
                    await server.container.shutdown()
                    logger.info("Test mode completed")
                    
                except Exception as e:
                    logger.error(f"Test failed: {e}")
                    sys.exit(1)
            
            asyncio.run(test_mode())
        
        elif command == "health":
            # 健康检查模式
            async def health_check():
                server = LogicServer()
                try:
                    await server.container.initialize([
                        "services/logic/services",
                        "services/logic/handlers", 
                        "services/logic/repositories"
                    ])
                    
                    health_info = await server.health_check()
                    print("Health Check Results:")
                    print(f"Server Status: {health_info['server_status']}")
                    print(f"Total Services: {health_info['container']['total_services']}")
                    print(f"Active Instances: {health_info['container']['active_instances']}")
                    
                    print("\nService Details:")
                    for service_name, health in health_info['services'].items():
                        status = health.get('status', 'unknown')
                        print(f"  {service_name}: {status}")
                    
                    await server.container.shutdown()
                    
                except Exception as e:
                    logger.error(f"Health check failed: {e}")
                    sys.exit(1)
            
            asyncio.run(health_check())
        
        else:
            print(f"Unknown command: {command}")
            print("Available commands: test, health")
            sys.exit(1)
    
    else:
        # 正常启动模式
        asyncio.run(main())