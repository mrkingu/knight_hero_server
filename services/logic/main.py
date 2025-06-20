"""
Logic逻辑服务主入口
Logic Service Main Entry

作者: lx
日期: 2025-06-20
描述: 服务启动入口、gRPC服务注册、定时任务初始化、优雅关闭
"""

import asyncio
import signal
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# 导入common框架组件
from common.grpc import grpc_service, grpc_method, start_grpc_server, register_service_instance
from common.database.core import RedisClient, MongoClient
from common.logger import get_logger

# 导入Logic服务组件
from .handlers import PlayerHandler, register_handler_class
from .services import PlayerService
from .ranking.rank_service import RankService
from .tasks import TaskManager, scheduled_task, distributed_lock

import logging

logger = logging.getLogger(__name__)


@grpc_service("logic", address="localhost", port=50051)
class LogicService:
    """Logic逻辑服务RPC接口"""
    
    def __init__(self):
        """初始化Logic服务"""
        # 初始化数据库客户端
        redis_config = {
            'host': 'localhost',
            'port': 6379,
            'db': 0
        }
        mongo_config = {
            'host': 'localhost',
            'port': 27017,
            'database': 'knight_hero'
        }
        
        self.redis_client = RedisClient(redis_config)
        self.mongo_client = MongoClient(mongo_config)
        
        # 业务服务
        self.player_service = PlayerService(self.redis_client, self.mongo_client)
        self.rank_service = RankService(self.redis_client)
        self.task_manager = TaskManager(self.redis_client)
        
        # 处理器
        self.player_handler = PlayerHandler()
        
        # 服务状态
        self.start_time = datetime.now()
        self.is_running = False
        
        logger.info("Logic服务初始化完成")
    
    async def initialize(self):
        """初始化服务"""
        try:
            # 连接数据库
            await self.redis_client.connect()
            await self.mongo_client.connect()
            
            # 注册处理器
            register_handler_class(self.player_handler)
            
            # 注册定时任务
            self.task_manager.register_scheduled_task(self)
            
            # 启动任务管理器
            await self.task_manager.start()
            
            # 启动清理任务
            asyncio.create_task(self._background_cleanup())
            
            self.is_running = True
            logger.info("Logic服务初始化成功")
            
        except Exception as e:
            logger.error(f"Logic服务初始化失败: {e}")
            raise
    
    async def shutdown(self):
        """关闭服务"""
        try:
            self.is_running = False
            logger.info("开始关闭Logic服务")
            
            # 停止任务管理器
            await self.task_manager.stop()
            
            # 处理在线玩家离线
            online_players = self.player_handler.get_online_players()
            for player_id in online_players:
                await self.player_handler.handle_player_offline(player_id)
            
            # 断开数据库连接
            await self.redis_client.disconnect()
            await self.mongo_client.disconnect()
            
            logger.info("Logic服务关闭完成")
            
        except Exception as e:
            logger.error(f"Logic服务关闭失败: {e}")
    
    # ==================== gRPC方法 ====================
    
    @grpc_method(timeout=5.0, description="获取玩家信息")
    async def get_player_info(self, player_id: str) -> Dict[str, Any]:
        """
        获取玩家信息
        
        Args:
            player_id: 玩家ID
            
        Returns:
            玩家信息字典
        """
        try:
            player_data = await self.player_service.get_by_id(player_id)
            if not player_data:
                return {"error": "玩家不存在"}
            
            # 获取排行榜信息
            level_rank = await self.rank_service.get_rank(
                RankService.RankType.LEVEL, player_id
            )
            wealth_rank = await self.rank_service.get_rank(
                RankService.RankType.WEALTH, player_id
            )
            
            result = dict(player_data)
            result.update({
                "level_rank": level_rank,
                "wealth_rank": wealth_rank,
                "is_online": player_id in self.player_handler.get_online_players()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"获取玩家信息失败 {player_id}: {e}")
            return {"error": str(e)}
    
    @grpc_method(timeout=3.0, description="更新玩家等级")
    async def update_player_level(self, player_id: str, new_level: int) -> bool:
        """
        更新玩家等级
        
        Args:
            player_id: 玩家ID
            new_level: 新等级
            
        Returns:
            是否成功
        """
        try:
            # 更新等级
            await self.player_service.update(player_id, {"level": new_level})
            
            # 更新排行榜
            player_data = await self.player_service.get_by_id(player_id)
            if player_data:
                await self.rank_service.update_level_rank(
                    player_id,
                    new_level,
                    {
                        "nickname": player_data.get("nickname", ""),
                        "vip_level": player_data.get("vip_level", 0)
                    }
                )
            
            logger.info(f"更新玩家等级: {player_id} -> {new_level}")
            return True
            
        except Exception as e:
            logger.error(f"更新玩家等级失败 {player_id}: {e}")
            return False
    
    @grpc_method(description="添加玩家资源")
    async def add_resources(
        self, 
        player_id: str, 
        gold: int = 0, 
        diamond: int = 0
    ) -> Dict[str, int]:
        """
        添加玩家资源
        
        Args:
            player_id: 玩家ID
            gold: 金币数量
            diamond: 钻石数量
            
        Returns:
            当前资源数量
        """
        try:
            result = {"gold": 0, "diamond": 0}
            
            # 添加金币
            if gold > 0:
                await self.player_service.add_gold(player_id, gold, "gm_add")
            
            # 添加钻石
            if diamond > 0:
                await self.player_service.add_diamond(player_id, diamond, "gm_add")
            
            # 获取当前资源
            player_data = await self.player_service.get_by_id(player_id)
            if player_data:
                result["gold"] = player_data.get("gold", 0)
                result["diamond"] = player_data.get("diamond", 0)
                
                # 更新财富排行榜
                wealth = result["gold"] + result["diamond"] * 10
                await self.rank_service.update_wealth_rank(
                    player_id,
                    wealth,
                    {
                        "nickname": player_data.get("nickname", ""),
                        "gold": result["gold"],
                        "diamond": result["diamond"]
                    }
                )
            
            logger.info(f"添加玩家资源: {player_id} 金币+{gold} 钻石+{diamond}")
            return result
            
        except Exception as e:
            logger.error(f"添加玩家资源失败 {player_id}: {e}")
            return {"gold": 0, "diamond": 0}
    
    @grpc_method(timeout=2.0, description="获取排行榜")
    async def get_ranking(
        self, 
        rank_type: str, 
        start: int = 0, 
        count: int = 10
    ) -> Dict[str, Any]:
        """
        获取排行榜
        
        Args:
            rank_type: 排行榜类型 (level/wealth/power/arena/vip)
            start: 起始位置
            count: 数量
            
        Returns:
            排行榜数据
        """
        try:
            # 转换排行榜类型
            rank_type_map = {
                "level": RankService.RankType.LEVEL,
                "wealth": RankService.RankType.WEALTH,
                "power": RankService.RankType.POWER,
                "arena": RankService.RankType.ARENA,
                "vip": RankService.RankType.VIP
            }
            
            if rank_type not in rank_type_map:
                return {"error": "无效的排行榜类型"}
            
            rank_enum = rank_type_map[rank_type]
            ranking_data = await self.rank_service.get_top_players(
                rank_enum, start, count
            )
            
            return {
                "rank_type": rank_type,
                "data": ranking_data,
                "total": len(ranking_data)
            }
            
        except Exception as e:
            logger.error(f"获取排行榜失败 {rank_type}: {e}")
            return {"error": str(e)}
    
    @grpc_method(description="获取服务状态")
    async def get_service_status(self) -> Dict[str, Any]:
        """
        获取服务状态
        
        Returns:
            服务状态信息
        """
        try:
            uptime = datetime.now() - self.start_time
            
            # 获取任务统计
            task_stats = await self.task_manager.get_task_stats()
            
            # 获取排行榜统计
            rank_stats = {}
            for rank_type in RankService.RankType:
                stats = await self.rank_service.get_rank_stats(rank_type)
                rank_stats[rank_type.value] = stats
            
            return {
                "service": "logic",
                "status": "running" if self.is_running else "stopped",
                "start_time": self.start_time.isoformat(),
                "uptime_seconds": int(uptime.total_seconds()),
                "online_players": self.player_handler.get_online_count(),
                "task_manager": task_stats,
                "rankings": rank_stats
            }
            
        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return {"error": str(e)}
    
    # ==================== 定时任务 ====================
    
    @scheduled_task(cron="0 0 * * *", description="每日重置任务")
    async def daily_reset(self):
        """每日重置处理"""
        try:
            async with distributed_lock("daily_reset", timeout=300):
                logger.info("开始执行每日重置任务")
                
                # 重置每日任务（这里可以扩展）
                await self._reset_daily_quests()
                
                # 重置每日商店（这里可以扩展）
                await self._reset_daily_shop()
                
                # 创建排行榜快照
                for rank_type in RankService.RankType:
                    await self.rank_service.create_snapshot(rank_type)
                
                logger.info("每日重置任务完成")
                
        except Exception as e:
            logger.error(f"每日重置任务失败: {e}")
    
    @scheduled_task(cron="*/10 * * * *", description="排行榜定时更新")
    async def update_rankings(self):
        """排行榜定时更新"""
        try:
            logger.debug("定时更新排行榜")
            
            # 获取所有在线玩家的最新数据，批量更新排行榜
            online_players = self.player_handler.get_online_players()
            
            if online_players:
                level_updates = {}
                wealth_updates = {}
                
                for player_id in online_players:
                    player_data = await self.player_service.get_by_id(player_id)
                    if player_data:
                        level = player_data.get("level", 1)
                        gold = player_data.get("gold", 0)
                        diamond = player_data.get("diamond", 0)
                        wealth = gold + diamond * 10
                        
                        level_updates[player_id] = float(level)
                        wealth_updates[player_id] = float(wealth)
                
                # 批量更新
                if level_updates:
                    await self.rank_service.batch_update_ranks(
                        RankService.RankType.LEVEL, level_updates
                    )
                
                if wealth_updates:
                    await self.rank_service.batch_update_ranks(
                        RankService.RankType.WEALTH, wealth_updates
                    )
            
        except Exception as e:
            logger.error(f"排行榜定时更新失败: {e}")
    
    @scheduled_task(cron="*/5 * * * *", description="清理不活跃玩家")
    async def cleanup_inactive_players(self):
        """清理不活跃玩家"""
        try:
            cleaned = await self.player_handler.cleanup_inactive_players(1800)  # 30分钟超时
            if cleaned > 0:
                logger.info(f"清理不活跃玩家: {cleaned}个")
                
        except Exception as e:
            logger.error(f"清理不活跃玩家失败: {e}")
    
    # ==================== 私有方法 ====================
    
    async def _reset_daily_quests(self):
        """重置每日任务"""
        # 这里可以实现每日任务重置逻辑
        logger.info("重置每日任务")
    
    async def _reset_daily_shop(self):
        """重置每日商店"""
        # 这里可以实现每日商店重置逻辑
        logger.info("重置每日商店")
    
    async def _background_cleanup(self):
        """后台清理任务"""
        while self.is_running:
            try:
                # 每5分钟执行一次清理
                await asyncio.sleep(300)
                
                if not self.is_running:
                    break
                
                # 清理过期的缓存数据等
                logger.debug("执行后台清理任务")
                
            except Exception as e:
                logger.error(f"后台清理任务异常: {e}")
                await asyncio.sleep(60)


async def main():
    """主函数"""
    # 创建Logic服务实例
    logic_service = LogicService()
    
    # 注册服务实例
    register_service_instance("logic", logic_service)
    
    # 设置信号处理
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("收到关闭信号")
        shutdown_event.set()
    
    # 注册信号处理器
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    
    try:
        # 初始化服务
        await logic_service.initialize()
        
        # 启动gRPC服务器
        server_task = asyncio.create_task(
            start_grpc_server(address="0.0.0.0", port=50051)
        )
        
        logger.info("Logic服务启动成功，端口: 50051")
        
        # 等待关闭信号
        await shutdown_event.wait()
        
    except KeyboardInterrupt:
        logger.info("收到键盘中断")
    except Exception as e:
        logger.error(f"Logic服务运行异常: {e}")
    finally:
        # 优雅关闭
        logger.info("开始优雅关闭Logic服务")
        await logic_service.shutdown()
        
        # 取消服务器任务
        if 'server_task' in locals():
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Logic服务已关闭")


if __name__ == "__main__":
    # 设置日志级别
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行服务
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("服务被用户中断")