#!/usr/bin/env python3
"""
启动器系统单元测试
Launcher System Unit Tests

作者: lx
日期: 2025-06-20
描述: 测试启动器各个模块的功能
"""

import pytest
import asyncio
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from launcher.supervisor_gen import SupervisorConfigGenerator, SupervisorConfig
from launcher.nginx_gen import NginxConfigGenerator, NginxGlobalConfig
from launcher.health_check import HealthCheckManager, HealthStatus
from launcher.launcher import Launcher


class TestSupervisorGenerator:
    """Supervisor配置生成器测试"""
    
    def setup_method(self):
        """设置测试数据"""
        self.test_config = {
            "services": {
                "gateway": {
                    "instances": 2,
                    "start_port": 8000,
                    "workers": 4,
                    "env": {"MAX_CONNECTIONS": 10000}
                },
                "logic": {
                    "instances": 1,
                    "start_port": 9000,
                    "workers": 4
                }
            }
        }
        
        self.supervisor_config = SupervisorConfig(
            project_dir="/test/project",
            environment="test"
        )
        
        self.generator = SupervisorConfigGenerator(
            self.test_config, 
            self.supervisor_config
        )
    
    def test_parse_services(self):
        """测试服务配置解析"""
        services = self.generator._parse_services()
        
        assert len(services) == 2
        assert services[0].name == "gateway"
        assert services[0].instances == 2
        assert services[0].start_port == 8000
        assert services[1].name == "logic"
        assert services[1].instances == 1
    
    def test_generate_main_config(self):
        """测试主配置生成"""
        config = self.generator.generate_main_config()
        
        assert "[supervisord]" in config
        assert "/var/log/game/supervisord.log" in config
        assert "PYTHONPATH" in config
    
    def test_generate_service_configs(self):
        """测试服务配置生成"""
        configs = self.generator.generate_service_configs()
        
        assert "gateway.conf" in configs
        assert "logic.conf" in configs
        assert "game_server_group.conf" in configs
        
        gateway_config = configs["gateway.conf"]
        assert "[program:gateway_1]" in gateway_config
        assert "[program:gateway_2]" in gateway_config
        assert "port 8000" in gateway_config or "port=8000" in gateway_config
    
    def test_get_program_list(self):
        """测试获取程序列表"""
        programs = self.generator.get_program_list()
        
        expected = ["gateway_1", "gateway_2", "logic_1"]
        assert programs == expected
    
    def test_validate_config(self):
        """测试配置验证"""
        errors = self.generator.validate_config()
        
        # 在测试环境中，项目目录不存在是正常的
        assert any("项目目录不可读" in error for error in errors)


class TestNginxGenerator:
    """Nginx配置生成器测试"""
    
    def setup_method(self):
        """设置测试数据"""
        self.test_config = {
            "services": {
                "gateway": {
                    "instances": 2,
                    "start_port": 8000
                },
                "logic": {
                    "instances": 1,
                    "start_port": 9000
                }
            },
            "nginx": {
                "workers": 4,
                "port": 80
            }
        }
        
        self.nginx_config = NginxGlobalConfig(worker_processes=4)
        self.generator = NginxConfigGenerator(self.test_config, self.nginx_config)
    
    def test_generate_upstreams(self):
        """测试上游配置生成"""
        upstreams = self.generator._generate_upstreams()
        
        assert len(upstreams) == 2
        assert upstreams[0].name == "gateway_cluster"
        assert len(upstreams[0].servers) == 2
        assert upstreams[0].servers[0].port == 8000
        assert upstreams[0].servers[1].port == 8001
    
    def test_generate_main_config(self):
        """测试主配置生成"""
        config = self.generator.generate_main_config()
        
        assert "worker_processes 4" in config
        assert "events {" in config
        assert "http {" in config
        assert "gzip on" in config
    
    def test_generate_upstream_config(self):
        """测试上游配置生成"""
        config = self.generator.generate_upstream_config()
        
        assert "upstream gateway_cluster" in config
        assert "upstream logic_cluster" in config
        assert "least_conn" in config
        assert "server 127.0.0.1:8000" in config
    
    def test_generate_server_config(self):
        """测试服务器配置生成"""
        config = self.generator.generate_server_config()
        
        assert "listen 80" in config
        assert "location /ws" in config
        assert "proxy_pass http://gateway_cluster" in config
        assert "upgrade" in config.lower()
    
    def test_validate_config(self):
        """测试配置验证"""
        errors = self.generator.validate_config()
        
        # 基本配置应该没有错误
        assert len(errors) == 0


class TestHealthCheckManager:
    """健康检查管理器测试"""
    
    def setup_method(self):
        """设置测试数据"""
        self.health_manager = HealthCheckManager()
        self.test_config = {
            "services": {
                "gateway": {
                    "instances": 1,
                    "start_port": 8000
                }
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            },
            "mongodb": {
                "uri": "mongodb://localhost:27017/test"
            }
        }
    
    @pytest.mark.asyncio
    async def test_http_health_check_timeout(self):
        """测试HTTP健康检查超时"""
        result = await self.health_manager.http_checker.check(
            "http://localhost:9999/health"  # 不存在的端口
        )
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "error" in result.details
    
    @pytest.mark.asyncio
    async def test_redis_health_check_timeout(self):
        """测试Redis健康检查超时"""
        result = await self.health_manager.redis_checker.check(
            host="localhost",
            port=9999  # 不存在的端口
        )
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "error" in result.details
    
    @pytest.mark.asyncio
    async def test_mongo_health_check_timeout(self):
        """测试MongoDB健康检查超时"""
        result = await self.health_manager.mongo_checker.check(
            "mongodb://localhost:9999/test"  # 不存在的端口
        )
        
        assert result.status == HealthStatus.UNHEALTHY
        assert "error" in result.details
    
    def test_get_health_summary(self):
        """测试健康检查摘要"""
        from launcher.health_check import HealthCheckResult
        
        results = [
            HealthCheckResult("service1", HealthStatus.HEALTHY, 0.1, {}, 123456),
            HealthCheckResult("service2", HealthStatus.UNHEALTHY, 0.2, {}, 123456),
            HealthCheckResult("service3", HealthStatus.HEALTHY, 0.15, {}, 123456)
        ]
        
        summary = self.health_manager.get_health_summary(results)
        
        assert summary["total_services"] == 3
        assert summary["healthy_services"] == 2
        assert summary["unhealthy_services"] == 1
        assert abs(summary["health_percentage"] - 66.67) < 0.01  # ~66.67%
        assert abs(summary["average_response_time"] - 0.15) < 0.001


class TestLauncher:
    """启动器主类测试"""
    
    def setup_method(self):
        """设置测试数据"""
        # 创建临时配置文件
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_file = self.temp_dir / "test_config.yaml"
        
        test_config = {
            "environment": "test",
            "services": {
                "gateway": {
                    "instances": 1,
                    "start_port": 8000,
                    "workers": 2
                }
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            },
            "mongodb": {
                "uri": "mongodb://localhost:27017/test"
            },
            "nginx": {
                "workers": 2,
                "port": 80
            }
        }
        
        with open(self.config_file, "w") as f:
            yaml.dump(test_config, f)
        
        self.launcher = Launcher(str(self.config_file))
    
    def test_load_config(self):
        """测试配置加载"""
        success = self.launcher._load_config()
        
        assert success is True
        assert self.launcher.config["environment"] == "test"
        assert "gateway" in self.launcher.config["services"]
    
    def test_command_exists(self):
        """测试命令存在检查"""
        # 测试存在的命令
        assert self.launcher._command_exists("ls") is True
        assert self.launcher._command_exists("python") is True
        
        # 测试不存在的命令
        assert self.launcher._command_exists("nonexistent_command_12345") is False
    
    @pytest.mark.asyncio
    async def test_initialize(self):
        """测试初始化"""
        with patch.object(self.launcher, '_check_environment', new_callable=AsyncMock):
            success = await self.launcher.initialize()
            
            assert success is True
            assert self.launcher.supervisor_generator is not None
            assert self.launcher.nginx_generator is not None
    
    @pytest.mark.asyncio
    async def test_is_port_in_use(self):
        """测试端口占用检查"""
        # 测试明显不会被占用的端口
        result = await self.launcher._is_port_in_use(65432)
        assert isinstance(result, bool)
    
    def teardown_method(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_integration_config_generation():
    """集成测试：配置生成"""
    test_config = {
        "environment": "test",
        "services": {
            "gateway": {
                "instances": 1,
                "start_port": 8000,
                "workers": 2
            },
            "logic": {
                "instances": 1,
                "start_port": 9000,
                "workers": 2
            }
        },
        "redis": {
            "host": "localhost",
            "port": 6379
        },
        "mongodb": {
            "uri": "mongodb://localhost:27017/test"
        },
        "nginx": {
            "workers": 2,
            "port": 80
        }
    }
    
    # 测试Supervisor配置生成
    supervisor_config = SupervisorConfig(
        project_dir="/test",
        environment="test"
    )
    supervisor_gen = SupervisorConfigGenerator(test_config, supervisor_config)
    
    # 验证生成的配置
    main_config = supervisor_gen.generate_main_config()
    service_configs = supervisor_gen.generate_service_configs()
    
    assert "[supervisord]" in main_config
    assert "gateway.conf" in service_configs
    assert "logic.conf" in service_configs
    
    # 测试Nginx配置生成
    nginx_config = NginxGlobalConfig(worker_processes=2)
    nginx_gen = NginxConfigGenerator(test_config, nginx_config)
    
    # 验证生成的配置
    nginx_main = nginx_gen.generate_main_config()
    upstream_config = nginx_gen.generate_upstream_config()
    
    assert "worker_processes 2" in nginx_main
    assert "upstream gateway_cluster" in upstream_config
    assert "upstream logic_cluster" in upstream_config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])