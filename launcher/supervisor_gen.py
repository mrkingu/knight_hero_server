#!/usr/bin/env python3
"""
Supervisor配置生成器
Supervisor Configuration Generator

作者: lx
日期: 2025-06-20
描述: 根据配置文件自动生成supervisor配置，实现进程管理和自动重启
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import yaml

import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """服务配置数据类"""
    name: str
    instances: int
    start_port: int
    workers: int
    env: Dict[str, Any]


@dataclass
class SupervisorConfig:
    """Supervisor全局配置"""
    log_dir: str = "/var/log/game"
    pid_dir: str = "/var/run/supervisor"
    project_dir: str = "/opt/game_server"
    python_path: str = "/opt/game_server"
    environment: str = "production"
    max_startup_time: int = 60
    max_restart_attempts: int = 3


class SupervisorConfigGenerator:
    """Supervisor配置生成器"""
    
    def __init__(self, config: Dict[str, Any], supervisor_config: Optional[SupervisorConfig] = None):
        """
        初始化配置生成器
        
        Args:
            config: 系统配置字典
            supervisor_config: Supervisor全局配置
        """
        self.config = config
        self.supervisor_config = supervisor_config or SupervisorConfig()
        self.services = self._parse_services()
        
    def _parse_services(self) -> List[ServiceConfig]:
        """
        解析服务配置
        
        Returns:
            服务配置列表
        """
        services = []
        service_configs = self.config.get("services", {})
        
        for service_name, service_data in service_configs.items():
            service_config = ServiceConfig(
                name=service_name,
                instances=service_data.get("instances", 1),
                start_port=service_data.get("start_port", 8000),
                workers=service_data.get("workers", 4),
                env=service_data.get("env", {})
            )
            services.append(service_config)
            
        return services
    
    def generate_main_config(self) -> str:
        """
        生成主要的supervisord配置
        
        Returns:
            supervisord.conf配置内容
        """
        config_lines = [
            "; Supervisor配置文件",
            "; 由SupervisorConfigGenerator自动生成",
            f"; 生成时间: {self._get_timestamp()}",
            "",
            "[supervisord]",
            f"logfile={self.supervisor_config.log_dir}/supervisord.log",
            "logfile_maxbytes=50MB",
            "logfile_backups=10",
            "loglevel=info",
            f"pidfile={self.supervisor_config.pid_dir}/supervisord.pid",
            "nodaemon=false",
            "minfds=1024",
            "minprocs=200",
            f"environment=PYTHONPATH=\"{self.supervisor_config.python_path}\",ENV=\"{self.supervisor_config.environment}\"",
            "",
            "[supervisorctl]",
            "serverurl=unix:///var/run/supervisor/supervisor.sock",
            "",
            "[unix_http_server]",
            "file=/var/run/supervisor/supervisor.sock",
            "chmod=0700",
            "",
            "[rpcinterface:supervisor]",
            "supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface",
            "",
            "[include]",
            "files = /etc/supervisor/conf.d/*.conf",
            ""
        ]
        
        return "\\n".join(config_lines)
    
    def generate_service_configs(self) -> Dict[str, str]:
        """
        生成各个服务的supervisor配置
        
        Returns:
            服务名到配置内容的映射
        """
        service_configs = {}
        
        for service in self.services:
            config_content = self._generate_single_service_config(service)
            service_configs[f"{service.name}.conf"] = config_content
            
        # 生成服务组配置
        group_config = self._generate_group_config()
        service_configs["game_server_group.conf"] = group_config
        
        return service_configs
    
    def _generate_single_service_config(self, service: ServiceConfig) -> str:
        """
        生成单个服务的配置
        
        Args:
            service: 服务配置
            
        Returns:
            配置内容字符串
        """
        config_lines = [
            f"; {service.name.title()}服务配置",
            f"; 实例数: {service.instances}",
            f"; 起始端口: {service.start_port}",
            ""
        ]
        
        # 为每个实例生成配置
        for i in range(service.instances):
            instance_id = i + 1
            port = service.start_port + i
            
            # 构建启动命令
            if service.name == "gateway":
                # Gateway服务使用uvicorn启动
                command = f"uvicorn services.{service.name}.main:get_app --host 0.0.0.0 --port {port} --workers {service.workers}"
            else:
                # 其他服务使用Python模块启动
                command = f"python -m services.{service.name}.main --port={port} --workers={service.workers}"
            
            # 环境变量
            env_vars = [f"PYTHONPATH=\"{self.supervisor_config.python_path}\"", 
                       f"ENV=\"{self.supervisor_config.environment}\""]
            
            # 添加服务特定的环境变量
            for key, value in service.env.items():
                env_vars.append(f"{key}=\"{value}\"")
            
            environment_str = ",".join(env_vars)
            
            # 生成配置块
            program_lines = [
                f"[program:{service.name}_{instance_id}]",
                f"command={command}",
                f"directory={self.supervisor_config.project_dir}",
                "autostart=true",
                "autorestart=true",
                f"startretries={self.supervisor_config.max_restart_attempts}",
                f"startsecs={min(10, self.supervisor_config.max_startup_time // 6)}",
                "user=game",
                f"stderr_logfile={self.supervisor_config.log_dir}/{service.name}_{instance_id}_err.log",
                f"stdout_logfile={self.supervisor_config.log_dir}/{service.name}_{instance_id}_out.log",
                "stderr_logfile_maxbytes=10MB",
                "stdout_logfile_maxbytes=10MB",
                "stderr_logfile_backups=5",
                "stdout_logfile_backups=5",
                f"environment={environment_str}",
                "redirect_stderr=false",
                "stopwaitsecs=30",
                "killasgroup=true",
                "stopasgroup=true",
                ""
            ]
            
            config_lines.extend(program_lines)
        
        return "\\n".join(config_lines)
    
    def _generate_group_config(self) -> str:
        """
        生成服务组配置
        
        Returns:
            组配置内容
        """
        # 收集所有程序名称
        program_names = []
        for service in self.services:
            for i in range(service.instances):
                program_names.append(f"{service.name}_{i + 1}")
        
        config_lines = [
            "; 游戏服务器进程组配置",
            "[group:game_server]",
            f"programs={','.join(program_names)}",
            "priority=999",
            ""
        ]
        
        return "\\n".join(config_lines)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def generate_startup_script(self) -> str:
        """
        生成启动脚本
        
        Returns:
            启动脚本内容
        """
        script_lines = [
            "#!/bin/bash",
            "# 游戏服务器启动脚本",
            "# 由SupervisorConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "set -e",
            "",
            "# 配置变量",
            f"PROJECT_DIR=\"{self.supervisor_config.project_dir}\"",
            f"LOG_DIR=\"{self.supervisor_config.log_dir}\"",
            f"PID_DIR=\"{self.supervisor_config.pid_dir}\"",
            "",
            "# 创建必要的目录",
            "echo \"创建必要的目录...\"",
            "sudo mkdir -p $LOG_DIR",
            "sudo mkdir -p $PID_DIR",
            "sudo mkdir -p /etc/supervisor/conf.d",
            "",
            "# 设置目录权限",
            "echo \"设置目录权限...\"",
            "sudo chown -R game:game $LOG_DIR",
            "sudo chown -R root:root $PID_DIR",
            "",
            "# 检查项目目录",
            "if [ ! -d \"$PROJECT_DIR\" ]; then",
            "    echo \"错误: 项目目录不存在: $PROJECT_DIR\"",
            "    exit 1",
            "fi",
            "",
            "# 启动supervisor",
            "echo \"启动supervisord...\"",
            "sudo supervisord -c /etc/supervisor/supervisord.conf",
            "",
            "# 等待supervisor启动",
            "echo \"等待supervisord启动...\"",
            "sleep 2",
            "",
            "# 启动所有服务",
            "echo \"启动游戏服务...\"",
            "sudo supervisorctl start game_server:*",
            "",
            "# 显示状态",
            "echo \"显示服务状态...\"",
            "sudo supervisorctl status",
            "",
            "echo \"游戏服务器启动完成!\"",
            ""
        ]
        
        return "\\n".join(script_lines)
    
    def generate_stop_script(self) -> str:
        """
        生成停止脚本
        
        Returns:
            停止脚本内容
        """
        script_lines = [
            "#!/bin/bash",
            "# 游戏服务器停止脚本",
            "# 由SupervisorConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "set -e",
            "",
            "echo \"停止游戏服务...\"",
            "",
            "# 停止所有游戏服务",
            "sudo supervisorctl stop game_server:*",
            "",
            "# 等待服务停止",
            "echo \"等待服务停止...\"",
            "sleep 5",
            "",
            "# 停止supervisord",
            "echo \"停止supervisord...\"",
            "sudo supervisorctl shutdown",
            "",
            "echo \"游戏服务器已停止!\"",
            ""
        ]
        
        return "\\n".join(script_lines)
    
    def save_configs(self, output_dir: str) -> bool:
        """
        保存所有配置文件到指定目录
        
        Args:
            output_dir: 输出目录路径
            
        Returns:
            是否保存成功
        """
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 保存主配置文件
            main_config = self.generate_main_config()
            with open(output_path / "supervisord.conf", "w", encoding="utf-8") as f:
                f.write(main_config)
            
            # 保存服务配置文件
            service_configs = self.generate_service_configs()
            conf_d_dir = output_path / "conf.d"
            conf_d_dir.mkdir(exist_ok=True)
            
            for filename, content in service_configs.items():
                with open(conf_d_dir / filename, "w", encoding="utf-8") as f:
                    f.write(content)
            
            # 保存启动和停止脚本
            scripts_dir = output_path / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            
            startup_script = self.generate_startup_script()
            with open(scripts_dir / "start_game_server.sh", "w", encoding="utf-8") as f:
                f.write(startup_script)
            
            stop_script = self.generate_stop_script()
            with open(scripts_dir / "stop_game_server.sh", "w", encoding="utf-8") as f:
                f.write(stop_script)
            
            # 设置脚本执行权限
            os.chmod(scripts_dir / "start_game_server.sh", 0o755)
            os.chmod(scripts_dir / "stop_game_server.sh", 0o755)
            
            logger.info(f"Supervisor配置文件已保存到: {output_dir}")
            return True
            
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def get_program_list(self) -> List[str]:
        """
        获取所有程序名称列表
        
        Returns:
            程序名称列表
        """
        programs = []
        for service in self.services:
            for i in range(service.instances):
                programs.append(f"{service.name}_{i + 1}")
        return programs
    
    def validate_config(self) -> List[str]:
        """
        验证配置的有效性
        
        Returns:
            验证错误列表，空列表表示无错误
        """
        errors = []
        
        # 检查基本配置
        if not self.services:
            errors.append("没有配置任何服务")
        
        # 检查端口冲突
        used_ports = set()
        for service in self.services:
            for i in range(service.instances):
                port = service.start_port + i
                if port in used_ports:
                    errors.append(f"端口冲突: {port}")
                used_ports.add(port)
        
        # 检查目录权限
        if not os.access(self.supervisor_config.project_dir, os.R_OK):
            errors.append(f"项目目录不可读: {self.supervisor_config.project_dir}")
        
        return errors


def load_config_from_yaml(config_file: str) -> Dict[str, Any]:
    """
    从YAML文件加载配置
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        配置字典
    """
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}


def main():
    """主函数，用于测试"""
    # 加载配置
    config_file = Path(__file__).parent / "config.yaml"
    config = load_config_from_yaml(str(config_file))
    
    if not config:
        print("配置文件加载失败")
        return
    
    # 创建配置生成器
    supervisor_config = SupervisorConfig(
        project_dir=str(Path(__file__).parent.parent.absolute()),
        environment="development"
    )
    
    generator = SupervisorConfigGenerator(config, supervisor_config)
    
    # 验证配置
    errors = generator.validate_config()
    if errors:
        print("配置验证失败:")
        for error in errors:
            print(f"  - {error}")
        return
    
    # 生成配置文件
    output_dir = "/tmp/supervisor_configs"
    success = generator.save_configs(output_dir)
    
    if success:
        print(f"Supervisor配置已生成: {output_dir}")
        print(f"程序列表: {generator.get_program_list()}")
    else:
        print("配置生成失败")


if __name__ == "__main__":
    main()