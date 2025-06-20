#!/usr/bin/env python3
"""
Nginx配置生成器
Nginx Configuration Generator

作者: lx
日期: 2025-06-20
描述: 自动生成Nginx配置，支持负载均衡、WebSocket、健康检查
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import yaml

import logging

logger = logging.getLogger(__name__)


@dataclass
class UpstreamServer:
    """上游服务器配置"""
    host: str
    port: int
    weight: int = 1
    max_fails: int = 3
    fail_timeout: str = "30s"
    backup: bool = False


@dataclass
class UpstreamConfig:
    """上游配置"""
    name: str
    servers: List[UpstreamServer]
    load_balancing: str = "least_conn"  # round_robin, least_conn, ip_hash
    keepalive: int = 300
    health_check: bool = True


@dataclass
class LocationConfig:
    """Location配置"""
    path: str
    upstream: Optional[str] = None
    proxy_pass: Optional[str] = None
    websocket: bool = False
    additional_headers: Optional[Dict[str, str]] = None
    cache_enabled: bool = False
    cache_time: str = "1h"
    
    def __post_init__(self):
        if self.additional_headers is None:
            self.additional_headers = {}


@dataclass
class ServerConfig:
    """服务器配置"""
    listen_port: int
    server_name: str = "_"
    locations: Optional[List[LocationConfig]] = None
    ssl_enabled: bool = False
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    
    def __post_init__(self):
        if self.locations is None:
            self.locations = []


@dataclass
class NginxGlobalConfig:
    """Nginx全局配置"""
    worker_processes: int = 4
    worker_connections: int = 1024
    keepalive_timeout: int = 65
    client_max_body_size: str = "64M"
    gzip_enabled: bool = True
    log_dir: str = "/var/log/nginx"
    access_log_format: str = "combined"


class NginxConfigGenerator:
    """Nginx配置生成器"""
    
    def __init__(self, config: Dict[str, Any], nginx_config: Optional[NginxGlobalConfig] = None):
        """
        初始化Nginx配置生成器
        
        Args:
            config: 系统配置字典
            nginx_config: Nginx全局配置
        """
        self.config = config
        self.nginx_config = nginx_config or NginxGlobalConfig()
        self.upstreams = self._generate_upstreams()
        self.servers = self._generate_servers()
    
    def _generate_upstreams(self) -> List[UpstreamConfig]:
        """
        生成上游配置
        
        Returns:
            上游配置列表
        """
        upstreams = []
        services = self.config.get("services", {})
        
        for service_name, service_config in services.items():
            instances = service_config.get("instances", 1)
            start_port = service_config.get("start_port", 8000)
            
            servers = []
            for i in range(instances):
                port = start_port + i
                server = UpstreamServer(
                    host="127.0.0.1",
                    port=port,
                    weight=1,
                    max_fails=3,
                    fail_timeout="30s"
                )
                servers.append(server)
            
            upstream = UpstreamConfig(
                name=f"{service_name}_cluster",
                servers=servers,
                load_balancing="least_conn",
                keepalive=300,
                health_check=True
            )
            upstreams.append(upstream)
        
        return upstreams
    
    def _generate_servers(self) -> List[ServerConfig]:
        """
        生成服务器配置
        
        Returns:
            服务器配置列表
        """
        nginx_port = self.config.get("nginx", {}).get("port", 80)
        
        # Gateway WebSocket locations
        gateway_locations = [
            LocationConfig(
                path="/ws",
                upstream="gateway_cluster",
                websocket=True,
                additional_headers={
                    "X-Real-IP": "$remote_addr",
                    "X-Forwarded-For": "$proxy_add_x_forwarded_for",
                    "X-Forwarded-Proto": "$scheme"
                }
            ),
            LocationConfig(
                path="/health",
                proxy_pass=None,  # 直接返回状态
                additional_headers={}
            ),
            LocationConfig(
                path="/api/",
                upstream="gateway_cluster",
                additional_headers={
                    "X-Real-IP": "$remote_addr",
                    "X-Forwarded-For": "$proxy_add_x_forwarded_for"
                }
            )
        ]
        
        # 静态文件location
        static_locations = [
            LocationConfig(
                path="/static/",
                proxy_pass=None,
                cache_enabled=True,
                cache_time="7d",
                additional_headers={
                    "Cache-Control": "public, max-age=604800"
                }
            )
        ]
        
        all_locations = gateway_locations + static_locations
        
        server = ServerConfig(
            listen_port=nginx_port,
            server_name="_",
            locations=all_locations
        )
        
        return [server]
    
    def generate_main_config(self) -> str:
        """
        生成主要的nginx.conf配置
        
        Returns:
            nginx.conf配置内容
        """
        config_lines = [
            "# Nginx主配置文件",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            f"user nginx;",
            f"worker_processes {self.nginx_config.worker_processes};",
            "error_log /var/log/nginx/error.log warn;",
            "pid /var/run/nginx.pid;",
            "",
            "events {",
            f"    worker_connections {self.nginx_config.worker_connections};",
            "    use epoll;",
            "    multi_accept on;",
            "}",
            "",
            "http {",
            "    include /etc/nginx/mime.types;",
            "    default_type application/octet-stream;",
            "",
            "    # 日志格式",
            f"    log_format main '$remote_addr - $remote_user [$time_local] \"$request\" '",
            "                    '$status $body_bytes_sent \"$http_referer\" '",
            "                    '\"$http_user_agent\" \"$http_x_forwarded_for\"';",
            "",
            f"    access_log {self.nginx_config.log_dir}/access.log main;",
            "",
            "    # 基本设置",
            "    sendfile on;",
            "    tcp_nopush on;",
            "    tcp_nodelay on;",
            f"    keepalive_timeout {self.nginx_config.keepalive_timeout};",
            "    types_hash_max_size 2048;",
            f"    client_max_body_size {self.nginx_config.client_max_body_size};",
            "",
            "    # Gzip压缩",
            "    gzip on;" if self.nginx_config.gzip_enabled else "    gzip off;",
            "    gzip_vary on;",
            "    gzip_min_length 1024;",
            "    gzip_proxied any;",
            "    gzip_comp_level 6;",
            "    gzip_types",
            "        text/plain",
            "        text/css",
            "        text/xml",
            "        text/javascript",
            "        application/json",
            "        application/javascript",
            "        application/xml+rss",
            "        application/atom+xml",
            "        image/svg+xml;",
            "",
            "    # 包含上游和虚拟主机配置",
            "    include /etc/nginx/conf.d/*.conf;",
            "}",
            ""
        ]
        
        return "\\n".join(config_lines)
    
    def generate_upstream_config(self) -> str:
        """
        生成上游配置
        
        Returns:
            上游配置内容
        """
        config_lines = [
            "# 上游服务器配置",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            ""
        ]
        
        for upstream in self.upstreams:
            # 上游块开始
            upstream_lines = [
                f"upstream {upstream.name} {{",
                f"    {upstream.load_balancing};"
            ]
            
            # 添加服务器
            for server in upstream.servers:
                server_line = f"    server {server.host}:{server.port}"
                
                # 添加服务器参数
                params = []
                if server.weight != 1:
                    params.append(f"weight={server.weight}")
                if server.max_fails != 3:
                    params.append(f"max_fails={server.max_fails}")
                if server.fail_timeout != "30s":
                    params.append(f"fail_timeout={server.fail_timeout}")
                if server.backup:
                    params.append("backup")
                
                if params:
                    server_line += " " + " ".join(params)
                
                server_line += ";"
                upstream_lines.append(server_line)
            
            # 添加keepalive
            if upstream.keepalive > 0:
                upstream_lines.append(f"    keepalive {upstream.keepalive};")
            
            # 健康检查 (需要nginx-plus或第三方模块)
            if upstream.health_check:
                upstream_lines.append("    # health_check;")
            
            upstream_lines.extend(["}", ""])
            config_lines.extend(upstream_lines)
        
        return "\\n".join(config_lines)
    
    def generate_server_config(self) -> str:
        """
        生成服务器配置
        
        Returns:
            服务器配置内容
        """
        config_lines = [
            "# 虚拟主机配置",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            ""
        ]
        
        for server in self.servers:
            server_lines = [
                "server {",
                f"    listen {server.listen_port};",
                f"    server_name {server.server_name};",
                ""
            ]
            
            # SSL配置
            if server.ssl_enabled and server.ssl_cert and server.ssl_key:
                server_lines.extend([
                    f"    listen {server.listen_port} ssl;",
                    f"    ssl_certificate {server.ssl_cert};",
                    f"    ssl_certificate_key {server.ssl_key};",
                    "    ssl_protocols TLSv1.2 TLSv1.3;",
                    "    ssl_ciphers ECDHE+AESGCM:ECDHE+AES256:ECDHE+AES128:!aNULL:!MD5:!DSS;",
                    "    ssl_prefer_server_ciphers on;",
                    ""
                ])
            
            # Location配置
            if server.locations:
                for location in server.locations:
                    location_lines = self._generate_location_config(location)
                    server_lines.extend(location_lines)
            
            server_lines.extend(["}", ""])
            config_lines.extend(server_lines)
        
        return "\\n".join(config_lines)
    
    def _generate_location_config(self, location: LocationConfig) -> List[str]:
        """
        生成单个location配置
        
        Args:
            location: Location配置
            
        Returns:
            配置行列表
        """
        lines = [f"    location {location.path} {{"]
        
        # 特殊处理health端点
        if location.path == "/health":
            lines.extend([
                "        access_log off;",
                "        return 200 'healthy\\\\n';",
                "        add_header Content-Type text/plain;",
                "    }",
                ""
            ])
            return lines
        
        # 静态文件处理
        if location.path.startswith("/static/"):
            lines.extend([
                "        alias /opt/game_server/static/;",
                "        expires 7d;",
                "        add_header Cache-Control \"public, immutable\";",
                "        add_header Vary Accept-Encoding;",
                "    }",
                ""
            ])
            return lines
        
        # 代理配置
        if location.upstream:
            lines.append(f"        proxy_pass http://{location.upstream};")
        elif location.proxy_pass:
            lines.append(f"        proxy_pass {location.proxy_pass};")
        
        # 基本代理头
        lines.extend([
            "        proxy_http_version 1.1;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;"
        ])
        
        # WebSocket支持
        if location.websocket:
            lines.extend([
                "        proxy_set_header Upgrade $http_upgrade;",
                "        proxy_set_header Connection \"upgrade\";",
                "        proxy_read_timeout 300s;",
                "        proxy_send_timeout 300s;",
                "        proxy_connect_timeout 75s;"
            ])
        
        # 额外的头部
        if location.additional_headers:
            for header, value in location.additional_headers.items():
                if not header.startswith("X-") or header not in ["X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"]:
                    lines.append(f"        proxy_set_header {header} {value};")
        
        # 缓存配置
        if location.cache_enabled:
            lines.extend([
                f"        expires {location.cache_time};",
                "        add_header Cache-Control \"public\";",
                "        add_header Vary Accept-Encoding;"
            ])
        
        lines.extend(["    }", ""])
        return lines
    
    def generate_security_config(self) -> str:
        """
        生成安全配置
        
        Returns:
            安全配置内容
        """
        config_lines = [
            "# 安全配置",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "# 隐藏Nginx版本",
            "server_tokens off;",
            "",
            "# 安全头部",
            "add_header X-Frame-Options DENY;",
            "add_header X-Content-Type-Options nosniff;",
            "add_header X-XSS-Protection \"1; mode=block\";",
            "add_header Referrer-Policy \"strict-origin-when-cross-origin\";",
            "",
            "# 限制请求方法",
            "if ($request_method !~ ^(GET|HEAD|POST|PUT|DELETE|OPTIONS)$ ) {",
            "    return 405;",
            "}",
            "",
            "# 限制文件上传大小",
            f"client_max_body_size {self.nginx_config.client_max_body_size};",
            "",
            "# 超时设置",
            "client_body_timeout 12;",
            "client_header_timeout 12;",
            "send_timeout 10;",
            ""
        ]
        
        return "\\n".join(config_lines)
    
    def generate_monitoring_config(self) -> str:
        """
        生成监控配置
        
        Returns:
            监控配置内容
        """
        config_lines = [
            "# 监控配置",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "server {",
            "    listen 8080;",
            "    server_name localhost;",
            "",
            "    location /nginx_status {",
            "        stub_status on;",
            "        access_log off;",
            "        allow 127.0.0.1;",
            "        allow 172.16.0.0/12;",
            "        allow 192.168.0.0/16;",
            "        allow 10.0.0.0/8;",
            "        deny all;",
            "    }",
            "",
            "    location /upstream_status {",
            "        # 需要nginx-plus或第三方模块",
            "        # upstream_show;",
            "        access_log off;",
            "        allow 127.0.0.1;",
            "        deny all;",
            "    }",
            "}",
            ""
        ]
        
        return "\\n".join(config_lines)
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
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
            with open(output_path / "nginx.conf", "w", encoding="utf-8") as f:
                f.write(main_config)
            
            # 保存conf.d目录配置
            conf_d_dir = output_path / "conf.d"
            conf_d_dir.mkdir(exist_ok=True)
            
            # 上游配置
            upstream_config = self.generate_upstream_config()
            with open(conf_d_dir / "upstream.conf", "w", encoding="utf-8") as f:
                f.write(upstream_config)
            
            # 服务器配置
            server_config = self.generate_server_config()
            with open(conf_d_dir / "default.conf", "w", encoding="utf-8") as f:
                f.write(server_config)
            
            # 安全配置
            security_config = self.generate_security_config()
            with open(conf_d_dir / "security.conf", "w", encoding="utf-8") as f:
                f.write(security_config)
            
            # 监控配置
            monitoring_config = self.generate_monitoring_config()
            with open(conf_d_dir / "monitoring.conf", "w", encoding="utf-8") as f:
                f.write(monitoring_config)
            
            # 生成启动脚本
            self._generate_nginx_scripts(output_path)
            
            logger.info(f"Nginx配置文件已保存到: {output_dir}")
            return True
            
        except Exception as e:
            logger.error(f"保存Nginx配置文件失败: {e}")
            return False
    
    def _generate_nginx_scripts(self, output_path: Path) -> None:
        """
        生成Nginx启动脚本
        
        Args:
            output_path: 输出路径
        """
        scripts_dir = output_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        # 启动脚本
        start_script = [
            "#!/bin/bash",
            "# Nginx启动脚本",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "set -e",
            "",
            "echo \"启动Nginx...\"",
            "",
            "# 检查配置文件",
            "nginx -t -c /etc/nginx/nginx.conf",
            "",
            "# 启动Nginx",
            "nginx -c /etc/nginx/nginx.conf",
            "",
            "echo \"Nginx启动成功!\"",
            ""
        ]
        
        with open(scripts_dir / "start_nginx.sh", "w", encoding="utf-8") as f:
            f.write("\\n".join(start_script))
        
        # 停止脚本
        stop_script = [
            "#!/bin/bash",
            "# Nginx停止脚本",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "set -e",
            "",
            "echo \"停止Nginx...\"",
            "",
            "# 优雅停止Nginx",
            "nginx -s quit",
            "",
            "# 等待进程结束",
            "sleep 2",
            "",
            "echo \"Nginx已停止!\"",
            ""
        ]
        
        with open(scripts_dir / "stop_nginx.sh", "w", encoding="utf-8") as f:
            f.write("\\n".join(stop_script))
        
        # 重载脚本
        reload_script = [
            "#!/bin/bash",
            "# Nginx重载脚本",
            "# 由NginxConfigGenerator自动生成",
            f"# 生成时间: {self._get_timestamp()}",
            "",
            "set -e",
            "",
            "echo \"重载Nginx配置...\"",
            "",
            "# 检查配置文件",
            "nginx -t -c /etc/nginx/nginx.conf",
            "",
            "# 重载配置",
            "nginx -s reload",
            "",
            "echo \"Nginx配置重载成功!\"",
            ""
        ]
        
        with open(scripts_dir / "reload_nginx.sh", "w", encoding="utf-8") as f:
            f.write("\\n".join(reload_script))
        
        # 设置执行权限
        for script_file in scripts_dir.glob("*.sh"):
            os.chmod(script_file, 0o755)
    
    def validate_config(self) -> List[str]:
        """
        验证配置的有效性
        
        Returns:
            验证错误列表，空列表表示无错误
        """
        errors = []
        
        # 检查上游服务器
        if not self.upstreams:
            errors.append("没有配置任何上游服务器")
        
        # 检查端口冲突
        used_ports = set()
        for server in self.servers:
            if server.listen_port in used_ports:
                errors.append(f"端口冲突: {server.listen_port}")
            used_ports.add(server.listen_port)
        
        # 检查SSL配置
        for server in self.servers:
            if server.ssl_enabled:
                if not server.ssl_cert or not server.ssl_key:
                    errors.append("SSL已启用但缺少证书或密钥文件")
        
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
    nginx_config = NginxGlobalConfig(
        worker_processes=config.get("nginx", {}).get("workers", 4)
    )
    
    generator = NginxConfigGenerator(config, nginx_config)
    
    # 验证配置
    errors = generator.validate_config()
    if errors:
        print("配置验证失败:")
        for error in errors:
            print(f"  - {error}")
        return
    
    # 生成配置文件
    output_dir = "/tmp/nginx_configs"
    success = generator.save_configs(output_dir)
    
    if success:
        print(f"Nginx配置已生成: {output_dir}")
        print(f"上游服务器数量: {len(generator.upstreams)}")
    else:
        print("配置生成失败")


if __name__ == "__main__":
    main()