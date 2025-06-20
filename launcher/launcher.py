#!/usr/bin/env python3
"""
游戏服务器启动器主模块
Game Server Launcher Main Module

作者: lx
日期: 2025-06-20
描述: 实现一键启动系统，集成Supervisor进程管理和Nginx负载均衡
"""

import asyncio
import subprocess
import signal
import sys
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml

from .supervisor_gen import SupervisorConfigGenerator, SupervisorConfig
from .nginx_gen import NginxConfigGenerator, NginxGlobalConfig
from .health_check import HealthCheckManager, HealthStatus
import logging

logger = logging.getLogger(__name__)


class LauncherError(Exception):
    """启动器异常类"""
    pass


class ServiceStatus:
    """服务状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Launcher:
    """
    游戏服务器启动器
    
    负责整个游戏服务器系统的启动、停止、监控和管理
    """
    
    def __init__(self, config_file: str = "launcher/config.yaml"):
        """
        初始化启动器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config: Dict[str, Any] = {}
        self.project_root = Path(__file__).parent.parent.absolute()
        self.output_dir = self.project_root / "deploy_configs"
        
        # 组件实例
        self.supervisor_generator: Optional[SupervisorConfigGenerator] = None
        self.nginx_generator: Optional[NginxConfigGenerator] = None
        self.health_manager = HealthCheckManager()
        
        # 运行状态
        self.services_status: Dict[str, str] = {}
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # 进程引用
        self.supervisor_process: Optional[subprocess.Popen] = None
        self.nginx_process: Optional[subprocess.Popen] = None
        
    async def initialize(self) -> bool:
        """
        初始化启动器
        
        Returns:
            是否初始化成功
        """
        try:
            logger.info("正在初始化启动器...")
            
            # 加载配置文件
            if not self._load_config():
                raise LauncherError("配置文件加载失败")
            
            # 验证环境
            await self._check_environment()
            
            # 初始化配置生成器
            self._initialize_generators()
            
            # 创建输出目录
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info("启动器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"启动器初始化失败: {e}")
            return False
    
    def _load_config(self) -> bool:
        """
        加载配置文件
        
        Returns:
            是否加载成功
        """
        try:
            config_path = Path(self.config_file)
            if not config_path.is_absolute():
                config_path = self.project_root / config_path
            
            if not config_path.exists():
                logger.error(f"配置文件不存在: {config_path}")
                return False
            
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
            
            logger.info(f"配置文件加载成功: {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return False
    
    async def _check_environment(self) -> None:
        """
        检查运行环境
        
        Raises:
            LauncherError: 环境检查失败
        """
        logger.info("检查运行环境...")
        
        # 检查必要的命令
        required_commands = ["supervisord", "supervisorctl", "nginx"]
        missing_commands = []
        
        for cmd in required_commands:
            if not self._command_exists(cmd):
                missing_commands.append(cmd)
        
        if missing_commands:
            raise LauncherError(f"缺少必要命令: {', '.join(missing_commands)}")
        
        # 检查权限
        if os.geteuid() != 0:
            logger.warning("建议以root权限运行以获得完整功能")
        
        # 检查端口可用性
        await self._check_port_availability()
        
        logger.info("环境检查通过")
    
    def _command_exists(self, command: str) -> bool:
        """
        检查命令是否存在
        
        Args:
            command: 命令名称
            
        Returns:
            命令是否存在
        """
        try:
            subprocess.run(["which", command], 
                         check=True, 
                         capture_output=True, 
                         timeout=5)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    
    async def _check_port_availability(self) -> None:
        """
        检查端口可用性
        
        Raises:
            LauncherError: 端口被占用
        """
        used_ports = []
        
        # 检查服务端口
        services = self.config.get("services", {})
        for service_name, service_config in services.items():
            instances = service_config.get("instances", 1)
            start_port = service_config.get("start_port", 8000)
            
            for i in range(instances):
                port = start_port + i
                if await self._is_port_in_use(port):
                    used_ports.append(port)
        
        # 检查Nginx端口
        nginx_port = self.config.get("nginx", {}).get("port", 80)
        if await self._is_port_in_use(nginx_port):
            used_ports.append(nginx_port)
        
        if used_ports:
            raise LauncherError(f"以下端口已被占用: {', '.join(map(str, used_ports))}")
    
    async def _is_port_in_use(self, port: int) -> bool:
        """
        检查端口是否被占用
        
        Args:
            port: 端口号
            
        Returns:
            是否被占用
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "netstat", "-tlnp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                output = stdout.decode("utf-8")
                return f":{port} " in output
            
            return False
            
        except Exception:
            return False
    
    def _initialize_generators(self) -> None:
        """初始化配置生成器"""
        # Supervisor配置生成器
        supervisor_config = SupervisorConfig(
            project_dir=str(self.project_root),
            environment=self.config.get("environment", "production"),
            log_dir="/var/log/game",
            pid_dir="/var/run/supervisor"
        )
        self.supervisor_generator = SupervisorConfigGenerator(self.config, supervisor_config)
        
        # Nginx配置生成器
        nginx_settings = self.config.get("nginx", {})
        nginx_config = NginxGlobalConfig(
            worker_processes=nginx_settings.get("workers", 4),
            worker_connections=1024,
            log_dir="/var/log/nginx"
        )
        self.nginx_generator = NginxConfigGenerator(self.config, nginx_config)
    
    async def start_all(self) -> bool:
        """
        启动所有服务
        
        Returns:
            是否启动成功
        """
        try:
            logger.info("开始启动所有服务...")
            
            # 1. 检查环境
            await self._check_environment()
            
            # 2. 生成配置文件
            if not await self._generate_configs():
                raise LauncherError("配置文件生成失败")
            
            # 3. 启动基础服务
            await self._start_infrastructure_services()
            
            # 4. 启动Nginx
            if not await self._start_nginx():
                raise LauncherError("Nginx启动失败")
            
            # 5. 启动游戏服务
            if not await self._start_game_services():
                raise LauncherError("游戏服务启动失败")
            
            # 6. 等待服务健康
            if not await self.health_manager.wait_for_services_healthy(
                self.config, max_attempts=30, check_interval=2.0
            ):
                logger.warning("部分服务可能未完全健康，但继续运行")
            
            # 7. 注册信号处理器
            self._register_signal_handlers()
            
            self.is_running = True
            logger.info("所有服务启动成功!")
            return True
            
        except Exception as e:
            logger.error(f"启动服务失败: {e}")
            await self._cleanup_on_failure()
            return False
    
    async def _generate_configs(self) -> bool:
        """
        生成配置文件
        
        Returns:
            是否生成成功
        """
        logger.info("生成配置文件...")
        
        try:
            # 验证配置
            supervisor_errors = self.supervisor_generator.validate_config()
            nginx_errors = self.nginx_generator.validate_config()
            
            if supervisor_errors or nginx_errors:
                logger.error("配置验证失败:")
                for error in supervisor_errors + nginx_errors:
                    logger.error(f"  - {error}")
                return False
            
            # 生成Supervisor配置
            supervisor_dir = self.output_dir / "supervisor"
            if not self.supervisor_generator.save_configs(str(supervisor_dir)):
                logger.error("Supervisor配置生成失败")
                return False
            
            # 生成Nginx配置
            nginx_dir = self.output_dir / "nginx"
            if not self.nginx_generator.save_configs(str(nginx_dir)):
                logger.error("Nginx配置生成失败")
                return False
            
            logger.info("配置文件生成成功")
            return True
            
        except Exception as e:
            logger.error(f"生成配置文件失败: {e}")
            return False
    
    async def _start_infrastructure_services(self) -> None:
        """启动基础设施服务（Redis、MongoDB等）"""
        logger.info("检查基础设施服务...")
        
        # 检查Redis
        redis_config = self.config.get("redis", {})
        if redis_config:
            redis_result = await self.health_manager.redis_checker.check(
                host=redis_config.get("host", "localhost"),
                port=redis_config.get("port", 6379)
            )
            
            if redis_result.status != HealthStatus.HEALTHY:
                logger.warning(f"Redis服务不可用: {redis_result.details.get('error')}")
        
        # 检查MongoDB
        mongodb_config = self.config.get("mongodb", {})
        if mongodb_config:
            uri = mongodb_config.get("uri", "mongodb://localhost:27017/game")
            mongo_result = await self.health_manager.mongo_checker.check(uri)
            
            if mongo_result.status != HealthStatus.HEALTHY:
                logger.warning(f"MongoDB服务不可用: {mongo_result.details.get('error')}")
    
    async def _start_nginx(self) -> bool:
        """
        启动Nginx
        
        Returns:
            是否启动成功
        """
        logger.info("启动Nginx...")
        
        try:
            # 复制配置文件到系统目录
            await self._deploy_nginx_configs()
            
            # 测试配置文件
            test_proc = await asyncio.create_subprocess_exec(
                "nginx", "-t",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await test_proc.communicate()
            
            if test_proc.returncode != 0:
                logger.error(f"Nginx配置测试失败: {stderr.decode()}")
                return False
            
            # 启动Nginx
            self.nginx_process = await asyncio.create_subprocess_exec(
                "nginx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待启动
            await asyncio.sleep(2)
            
            # 检查进程状态
            if self.nginx_process.poll() is not None:
                logger.error("Nginx启动失败")
                return False
            
            logger.info("Nginx启动成功")
            return True
            
        except Exception as e:
            logger.error(f"启动Nginx失败: {e}")
            return False
    
    async def _deploy_nginx_configs(self) -> None:
        """部署Nginx配置文件到系统目录"""
        nginx_config_dir = self.output_dir / "nginx"
        
        # 复制主配置文件
        subprocess.run([
            "sudo", "cp", 
            str(nginx_config_dir / "nginx.conf"), 
            "/etc/nginx/nginx.conf"
        ], check=True)
        
        # 复制conf.d配置
        subprocess.run([
            "sudo", "cp", "-r",
            str(nginx_config_dir / "conf.d") + "/.",
            "/etc/nginx/conf.d/"
        ], check=True)
        
        logger.info("Nginx配置文件部署完成")
    
    async def _start_game_services(self) -> bool:
        """
        启动游戏服务
        
        Returns:
            是否启动成功
        """
        logger.info("启动游戏服务...")
        
        try:
            # 部署Supervisor配置
            await self._deploy_supervisor_configs()
            
            # 启动supervisord
            self.supervisor_process = await asyncio.create_subprocess_exec(
                "supervisord", "-c", "/etc/supervisor/supervisord.conf",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待supervisord启动
            await asyncio.sleep(3)
            
            # 启动所有游戏服务
            start_proc = await asyncio.create_subprocess_exec(
                "supervisorctl", "start", "game_server:*",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await start_proc.communicate()
            
            if start_proc.returncode != 0:
                logger.error(f"启动游戏服务失败: {stderr.decode()}")
                return False
            
            logger.info("游戏服务启动成功")
            logger.info(f"服务状态:\\n{stdout.decode()}")
            
            return True
            
        except Exception as e:
            logger.error(f"启动游戏服务失败: {e}")
            return False
    
    async def _deploy_supervisor_configs(self) -> None:
        """部署Supervisor配置文件到系统目录"""
        supervisor_config_dir = self.output_dir / "supervisor"
        
        # 复制主配置文件
        subprocess.run([
            "sudo", "cp",
            str(supervisor_config_dir / "supervisord.conf"),
            "/etc/supervisor/supervisord.conf"
        ], check=True)
        
        # 复制conf.d配置
        subprocess.run([
            "sudo", "cp", "-r",
            str(supervisor_config_dir / "conf.d") + "/.",
            "/etc/supervisor/conf.d/"
        ], check=True)
        
        logger.info("Supervisor配置文件部署完成")
    
    def _register_signal_handlers(self) -> None:
        """注册信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"接收到信号 {signum}，开始优雅关闭...")
            asyncio.create_task(self.stop_all())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def stop_all(self) -> bool:
        """
        停止所有服务
        
        Returns:
            是否停止成功
        """
        logger.info("开始停止所有服务...")
        
        try:
            self.is_running = False
            self.shutdown_event.set()
            
            # 停止游戏服务
            await self._stop_game_services()
            
            # 停止Nginx
            await self._stop_nginx()
            
            logger.info("所有服务已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止服务失败: {e}")
            return False
    
    async def _stop_game_services(self) -> None:
        """停止游戏服务"""
        logger.info("停止游戏服务...")
        
        try:
            # 停止所有游戏服务
            await asyncio.create_subprocess_exec(
                "supervisorctl", "stop", "game_server:*",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # 停止supervisord
            await asyncio.create_subprocess_exec(
                "supervisorctl", "shutdown",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            logger.info("游戏服务已停止")
            
        except Exception as e:
            logger.warning(f"停止游戏服务时出现错误: {e}")
    
    async def _stop_nginx(self) -> None:
        """停止Nginx"""
        logger.info("停止Nginx...")
        
        try:
            await asyncio.create_subprocess_exec(
                "nginx", "-s", "quit",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            logger.info("Nginx已停止")
            
        except Exception as e:
            logger.warning(f"停止Nginx时出现错误: {e}")
    
    async def _cleanup_on_failure(self) -> None:
        """启动失败时的清理工作"""
        logger.info("执行故障清理...")
        
        try:
            await self.stop_all()
        except Exception as e:
            logger.error(f"清理失败: {e}")
    
    async def get_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            系统状态信息
        """
        # 执行健康检查
        health_results = await self.health_manager.check_service_health(self.config)
        health_summary = self.health_manager.get_health_summary(health_results)
        
        # 获取Supervisor状态
        supervisor_status = await self._get_supervisor_status()
        
        return {
            "launcher": {
                "running": self.is_running,
                "config_file": self.config_file,
                "environment": self.config.get("environment", "unknown")
            },
            "health": health_summary,
            "supervisor": supervisor_status,
            "timestamp": time.time()
        }
    
    async def _get_supervisor_status(self) -> Dict[str, Any]:
        """
        获取Supervisor状态
        
        Returns:
            Supervisor状态信息
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "supervisorctl", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                status_lines = stdout.decode().strip().split("\\n")
                programs = {}
                
                for line in status_lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            programs[parts[0]] = parts[1]
                
                return {
                    "available": True,
                    "programs": programs
                }
            else:
                return {
                    "available": False,
                    "error": stderr.decode()
                }
                
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def restart_service(self, service_name: str) -> bool:
        """
        重启指定服务
        
        Args:
            service_name: 服务名称
            
        Returns:
            是否重启成功
        """
        logger.info(f"重启服务: {service_name}")
        
        try:
            # 重启服务的所有实例
            proc = await asyncio.create_subprocess_exec(
                "supervisorctl", "restart", f"game_server:{service_name}_*",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                logger.info(f"服务 {service_name} 重启成功")
                return True
            else:
                logger.error(f"服务 {service_name} 重启失败: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"重启服务 {service_name} 失败: {e}")
            return False
    
    async def wait_for_shutdown(self) -> None:
        """等待关闭信号"""
        await self.shutdown_event.wait()


async def main():
    """主函数，用于测试"""
    launcher = Launcher()
    
    # 初始化
    if not await launcher.initialize():
        logger.error("启动器初始化失败")
        return
    
    # 启动所有服务
    success = await launcher.start_all()
    if not success:
        logger.error("服务启动失败")
        return
    
    try:
        # 等待关闭信号
        await launcher.wait_for_shutdown()
    finally:
        # 停止所有服务
        await launcher.stop_all()


if __name__ == "__main__":
    asyncio.run(main())