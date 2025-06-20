"""
战斗服务主程序
Fight Service Main

作者: lx
日期: 2025-06-18
描述: 战斗服务启动程序，包含进程池初始化和性能监控
"""
import asyncio
import signal
import sys
import time
import os
from typing import Dict, Any, Optional
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing as mp
from dataclasses import dataclass
import json
import logging
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from .handlers.battle_handler import (
    BattleHandler, BattleRequest, BattleReport, BattleType, PlayerData
)
from .core.battle_engine import BattleEngine
from .utils.object_pool import get_pool_manager


@dataclass
class ServiceConfig:
    """服务配置"""
    host: str = "0.0.0.0"
    port: int = 8002
    workers: int = 4
    max_connections: int = 1000
    enable_performance_monitor: bool = True
    monitor_interval: float = 30.0
    log_level: str = "INFO"
    pool_config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.pool_config is None:
            self.pool_config = {
                "cpu_workers": min(4, mp.cpu_count()),
                "io_workers": 10,
                "battle_pool_size": 1000,
                "result_cache_size": 10000
            }


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, interval: float = 30.0):
        self.interval = interval
        self.running = False
        self.stats_history = []
        self.max_history = 100
        
    async def start_monitoring(self, battle_handler: BattleHandler) -> None:
        """开始性能监控
        
        Args:
            battle_handler: 战斗处理器
        """
        self.running = True
        
        while self.running:
            try:
                # 收集统计信息
                stats = self._collect_stats(battle_handler)
                
                # 记录到历史
                self.stats_history.append(stats)
                if len(self.stats_history) > self.max_history:
                    self.stats_history.pop(0)
                
                # 输出监控信息
                self._log_stats(stats)
                
                # 检查性能告警
                self._check_alerts(stats)
                
                await asyncio.sleep(self.interval)
                
            except Exception as e:
                logging.error(f"性能监控出错: {e}")
                await asyncio.sleep(self.interval)
    
    def _collect_stats(self, battle_handler: BattleHandler) -> Dict[str, Any]:
        """收集统计信息
        
        Args:
            battle_handler: 战斗处理器
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        import psutil
        import gc
        
        # 系统资源
        system_stats = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_mb": psutil.virtual_memory().used / 1024 / 1024,
            "disk_usage_percent": psutil.disk_usage('/').percent,
            "process_count": len(psutil.pids())
        }
        
        # 战斗服务统计
        battle_stats = battle_handler.get_stats()
        
        # 对象池统计
        pool_manager = get_pool_manager()
        pool_stats = pool_manager.get_all_stats()
        
        # Python GC 统计
        gc_stats = {
            "gc_counts": gc.get_count(),
            "gc_stats": gc.get_stats()
        }
        
        return {
            "timestamp": time.time(),
            "system": system_stats,
            "battle_service": battle_stats,
            "object_pools": pool_stats,
            "gc": gc_stats
        }
    
    def _log_stats(self, stats: Dict[str, Any]) -> None:
        """记录统计信息
        
        Args:
            stats: 统计信息
        """
        system = stats["system"]
        battle = stats["battle_service"]
        
        logging.info(
            f"性能监控 - "
            f"CPU: {system['cpu_percent']:.1f}%, "
            f"内存: {system['memory_percent']:.1f}%, "
            f"战斗总数: {battle['total_battles']}, "
            f"平均战斗时间: {battle['avg_battle_time']:.3f}s, "
            f"缓存命中率: {battle['cache_hits']/(battle['cache_hits']+battle['cache_misses'])*100:.1f}% "
            if (battle['cache_hits'] + battle['cache_misses']) > 0 else "缓存命中率: 0%"
        )
    
    def _check_alerts(self, stats: Dict[str, Any]) -> None:
        """检查性能告警
        
        Args:
            stats: 统计信息
        """
        system = stats["system"]
        battle = stats["battle_service"]
        
        # CPU 告警
        if system["cpu_percent"] > 90:
            logging.warning(f"CPU使用率过高: {system['cpu_percent']:.1f}%")
        
        # 内存告警
        if system["memory_percent"] > 90:
            logging.warning(f"内存使用率过高: {system['memory_percent']:.1f}%")
        
        # 错误率告警
        if battle["error_count"] > 0:
            error_rate = battle["error_count"] / battle["total_battles"] * 100
            if error_rate > 5:  # 错误率超过5%
                logging.warning(f"战斗错误率过高: {error_rate:.1f}%")
        
        # 平均战斗时间告警
        if battle["avg_battle_time"] > 5.0:  # 超过5秒
            logging.warning(f"平均战斗时间过长: {battle['avg_battle_time']:.3f}s")
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        self.running = False
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """获取统计摘要
        
        Returns:
            Dict[str, Any]: 统计摘要
        """
        if not self.stats_history:
            return {}
        
        recent_stats = self.stats_history[-1]
        
        # 计算趋势
        if len(self.stats_history) >= 2:
            prev_stats = self.stats_history[-2]
            cpu_trend = recent_stats["system"]["cpu_percent"] - prev_stats["system"]["cpu_percent"]
            memory_trend = recent_stats["system"]["memory_percent"] - prev_stats["system"]["memory_percent"]
        else:
            cpu_trend = 0
            memory_trend = 0
        
        return {
            "current_stats": recent_stats,
            "trends": {
                "cpu_trend": cpu_trend,
                "memory_trend": memory_trend
            },
            "history_count": len(self.stats_history)
        }


class FightService:
    """战斗服务"""
    
    def __init__(self, config: Optional[ServiceConfig] = None):
        """初始化战斗服务
        
        Args:
            config: 服务配置
        """
        self.config = config or ServiceConfig()
        self.battle_handler: Optional[BattleHandler] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        
        # 配置日志
        self._setup_logging()
        
        # 注册信号处理器
        self._setup_signal_handlers()
    
    def _setup_logging(self) -> None:
        """设置日志"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f"fight_service_{os.getpid()}.log")
            ]
        )
        
        # 设置特定模块的日志级别
        logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(sig, frame):
            logging.info(f"收到信号 {sig}，开始优雅关闭...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def start(self) -> None:
        """启动服务"""
        logging.info("战斗服务启动中...")
        
        try:
            # 初始化组件
            await self._initialize_components()
            
            # 启动性能监控
            if self.config.enable_performance_monitor:
                await self._start_performance_monitor()
            
            self.running = True
            logging.info(f"战斗服务已启动 - 端口: {self.config.port}, 工作进程: {self.config.workers}")
            
            # 主服务循环
            await self._run_service()
            
        except Exception as e:
            logging.error(f"战斗服务启动失败: {e}")
            raise
    
    async def _initialize_components(self) -> None:
        """初始化组件"""
        # 初始化战斗处理器
        self.battle_handler = BattleHandler()
        
        # 初始化性能监控器
        if self.config.enable_performance_monitor:
            self.performance_monitor = PerformanceMonitor(self.config.monitor_interval)
        
        logging.info("组件初始化完成")
    
    async def _start_performance_monitor(self) -> None:
        """启动性能监控"""
        if self.performance_monitor and self.battle_handler:
            asyncio.create_task(
                self.performance_monitor.start_monitoring(self.battle_handler)
            )
            logging.info("性能监控已启动")
    
    async def _run_service(self) -> None:
        """运行服务主循环"""
        try:
            # 等待关闭信号
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logging.info("服务主循环被取消")
    
    async def process_battle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理战斗请求
        
        Args:
            request_data: 请求数据
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        if not self.battle_handler:
            raise RuntimeError("战斗处理器未初始化")
        
        try:
            # 解析请求
            request = self._parse_battle_request(request_data)
            
            # 处理战斗
            report = await self.battle_handler.process_battle(request)
            
            # 返回结果
            return {
                "success": True,
                "data": report.to_dict()
            }
            
        except Exception as e:
            logging.error(f"处理战斗请求失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _parse_battle_request(self, request_data: Dict[str, Any]) -> BattleRequest:
        """解析战斗请求
        
        Args:
            request_data: 请求数据
            
        Returns:
            BattleRequest: 战斗请求对象
        """
        # 解析攻击方数据
        attacker_data = request_data.get("attacker", {})
        attacker = PlayerData(
            player_id=attacker_data.get("player_id", 0),
            name=attacker_data.get("name", ""),
            level=attacker_data.get("level", 1),
            units=attacker_data.get("units", []),
            formation=attacker_data.get("formation", []),
            team_power=attacker_data.get("team_power", 0),
            buffs=attacker_data.get("buffs", [])
        )
        
        # 解析防守方数据
        defender_data = request_data.get("defender", {})
        defender = PlayerData(
            player_id=defender_data.get("player_id", 0),
            name=defender_data.get("name", ""),
            level=defender_data.get("level", 1),
            units=defender_data.get("units", []),
            formation=defender_data.get("formation", []),
            team_power=defender_data.get("team_power", 0),
            buffs=defender_data.get("buffs", [])
        )
        
        # 创建战斗请求
        request = BattleRequest(
            battle_id=request_data.get("battle_id", f"battle_{int(time.time())}"),
            battle_type=BattleType(request_data.get("battle_type", "pve")),
            attacker=attacker,
            defender=defender,
            settings=request_data.get("settings", {})
        )
        
        return request
    
    async def get_battle_report(self, battle_id: str) -> Optional[Dict[str, Any]]:
        """获取战斗报告
        
        Args:
            battle_id: 战斗ID
            
        Returns:
            Optional[Dict[str, Any]]: 战斗报告
        """
        if not self.battle_handler:
            return None
        
        report = self.battle_handler.get_battle_report(battle_id)
        return report.to_dict() if report else None
    
    def get_service_stats(self) -> Dict[str, Any]:
        """获取服务统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = {
            "service_status": "running" if self.running else "stopped",
            "config": {
                "workers": self.config.workers,
                "max_connections": self.config.max_connections,
                "performance_monitor_enabled": self.config.enable_performance_monitor
            }
        }
        
        if self.battle_handler:
            stats["battle_handler"] = self.battle_handler.get_stats()
        
        if self.performance_monitor:
            stats["performance_monitor"] = self.performance_monitor.get_stats_summary()
        
        return stats
    
    async def shutdown(self) -> None:
        """关闭服务"""
        if not self.running:
            return
        
        logging.info("战斗服务关闭中...")
        self.running = False
        
        try:
            # 停止性能监控
            if self.performance_monitor:
                self.performance_monitor.stop_monitoring()
            
            # 关闭战斗处理器
            if self.battle_handler:
                self.battle_handler.shutdown()
            
            # 关闭对象池管理器
            pool_manager = get_pool_manager()
            pool_manager.shutdown()
            
            # 触发关闭事件
            self._shutdown_event.set()
            
            logging.info("战斗服务已关闭")
            
        except Exception as e:
            logging.error(f"战斗服务关闭时出错: {e}")


# 示例用法和测试函数
async def example_battle():
    """战斗示例"""
    # 创建示例数据
    attacker_units = [
        {
            "id": 1,
            "name": "战士",
            "hp": 150,
            "max_hp": 150,
            "atk": 80,
            "def": 40,
            "spd": 90,
            "skills": [1001, 1002],
            "ai_type": "aggressive"
        },
        {
            "id": 2,
            "name": "法师",
            "hp": 100,
            "max_hp": 100,
            "atk": 120,
            "def": 20,
            "spd": 110,
            "skills": [1001, 1003],
            "ai_type": "balanced"
        }
    ]
    
    defender_units = [
        {
            "id": 3,
            "name": "守卫",
            "hp": 200,
            "max_hp": 200,
            "atk": 60,
            "def": 60,
            "spd": 70,
            "skills": [1001],
            "ai_type": "defensive"
        }
    ]
    
    # 创建战斗请求
    request_data = {
        "battle_id": "example_battle_001",
        "battle_type": "pve",
        "attacker": {
            "player_id": 1001,
            "name": "玩家1",
            "level": 10,
            "units": attacker_units,
            "team_power": 500
        },
        "defender": {
            "player_id": 2001,
            "name": "怪物",
            "level": 8,
            "units": defender_units,
            "team_power": 300
        },
        "settings": {
            "max_rounds": 20
        }
    }
    
    # 创建服务
    service = FightService()
    await service._initialize_components()
    
    # 处理战斗
    result = await service.process_battle_request(request_data)
    
    print("战斗结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 关闭服务
    await service.shutdown()


async def main():
    """主函数"""
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="战斗服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8002, help="监听端口")
    parser.add_argument("--workers", type=int, default=4, help="工作进程数")
    parser.add_argument("--example", action="store_true", help="运行示例战斗")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    
    args = parser.parse_args()
    
    if args.example:
        # 运行示例
        await example_battle()
        return
    
    # 创建服务配置
    config = ServiceConfig(
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_level=args.log_level
    )
    
    # 创建并启动服务
    service = FightService(config)
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logging.info("收到中断信号")
    except Exception as e:
        logging.error(f"服务运行出错: {e}")
    finally:
        await service.shutdown()


if __name__ == "__main__":
    # 设置多进程启动方法
    mp.set_start_method('spawn', force=True)
    
    # 运行主函数
    asyncio.run(main())