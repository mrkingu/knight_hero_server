"""
排行榜服务
Ranking Service

作者: lx
日期: 2025-06-20
描述: Redis Sorted Set实现的多种排行榜、分页查询、定时快照
"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

from common.database.core import RedisClient

logger = logging.getLogger(__name__)


class RankType(Enum):
    """排行榜类型"""
    LEVEL = "level"          # 等级排行榜
    POWER = "power"          # 战力排行榜  
    ARENA = "arena"          # 竞技场排行榜
    WEALTH = "wealth"        # 财富排行榜
    VIP = "vip"             # VIP排行榜


class RankService:
    """排行榜服务"""
    
    def __init__(self, redis_client=None):
        """
        初始化排行榜服务
        
        Args:
            redis_client: Redis客户端
        """
        self.redis = redis_client or RedisClient({'host': 'localhost', 'port': 6379, 'db': 0})
        
        # 排行榜配置
        self.rank_configs = {
            RankType.LEVEL: {
                "key": "rank:level",
                "snapshot_key": "rank:level:snapshot",
                "max_size": 1000,
                "update_interval": 60  # 秒
            },
            RankType.POWER: {
                "key": "rank:power", 
                "snapshot_key": "rank:power:snapshot",
                "max_size": 1000,
                "update_interval": 300
            },
            RankType.ARENA: {
                "key": "rank:arena",
                "snapshot_key": "rank:arena:snapshot", 
                "max_size": 10000,
                "update_interval": 600
            },
            RankType.WEALTH: {
                "key": "rank:wealth",
                "snapshot_key": "rank:wealth:snapshot",
                "max_size": 500,
                "update_interval": 3600
            },
            RankType.VIP: {
                "key": "rank:vip",
                "snapshot_key": "rank:vip:snapshot",
                "max_size": 200,
                "update_interval": 7200
            }
        }
        
        # 最后更新时间
        self.last_update_times: Dict[RankType, float] = {}
    
    async def update_rank(
        self, 
        rank_type: RankType, 
        player_id: str, 
        score: float,
        player_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新玩家排行榜分数
        
        Args:
            rank_type: 排行榜类型
            player_id: 玩家ID
            score: 分数
            player_data: 玩家数据（用于存储额外信息）
            
        Returns:
            是否成功更新
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            # 更新分数
            await self.redis.client.zadd(rank_key, {player_id: score})
            
            # 存储玩家详细数据
            if player_data:
                data_key = f"{rank_key}:data:{player_id}"
                await self.redis.client.setex(
                    data_key,
                    86400,  # 24小时过期
                    json.dumps(player_data)
                )
            
            # 保持排行榜大小
            max_size = config["max_size"]
            current_size = await self.redis.client.zcard(rank_key)
            
            if current_size > max_size:
                # 删除分数最低的玩家
                to_remove = current_size - max_size
                await self.redis.client.zremrangebyrank(rank_key, 0, to_remove - 1)
            
            logger.debug(f"更新排行榜: {rank_type.value} 玩家:{player_id} 分数:{score}")
            return True
            
        except Exception as e:
            logger.error(f"更新排行榜失败 {rank_type.value} {player_id}: {e}")
            return False
    
    async def get_rank(self, rank_type: RankType, player_id: str) -> Optional[int]:
        """
        获取玩家排名
        
        Args:
            rank_type: 排行榜类型
            player_id: 玩家ID
            
        Returns:
            排名（从1开始），None表示未上榜
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            # 获取排名（Redis返回的是从0开始的索引）
            rank = await self.redis.client.zrevrank(rank_key, player_id)
            
            return rank + 1 if rank is not None else None
            
        except Exception as e:
            logger.error(f"获取排名失败 {rank_type.value} {player_id}: {e}")
            return None
    
    async def get_score(self, rank_type: RankType, player_id: str) -> Optional[float]:
        """
        获取玩家分数
        
        Args:
            rank_type: 排行榜类型
            player_id: 玩家ID
            
        Returns:
            分数，None表示未上榜
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            score = await self.redis.client.zscore(rank_key, player_id)
            return score
            
        except Exception as e:
            logger.error(f"获取分数失败 {rank_type.value} {player_id}: {e}")
            return None
    
    async def get_top_players(
        self, 
        rank_type: RankType, 
        start: int = 0, 
        count: int = 10,
        include_data: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取排行榜前N名
        
        Args:
            rank_type: 排行榜类型
            start: 起始位置（从0开始）
            count: 数量
            include_data: 是否包含玩家详细数据
            
        Returns:
            排行榜列表
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            # 获取排行榜数据（分数从高到低）
            results = await self.redis.client.zrevrange(
                rank_key, start, start + count - 1, withscores=True
            )
            
            ranking = []
            for i, (player_id, score) in enumerate(results):
                player_info = {
                    "rank": start + i + 1,
                    "player_id": player_id,
                    "score": int(score)
                }
                
                # 获取玩家详细数据
                if include_data:
                    data_key = f"{rank_key}:data:{player_id}"
                    data_json = await self.redis.client.get(data_key)
                    
                    if data_json:
                        try:
                            player_data = json.loads(data_json)
                            player_info.update(player_data)
                        except json.JSONDecodeError:
                            pass
                
                ranking.append(player_info)
            
            return ranking
            
        except Exception as e:
            logger.error(f"获取排行榜失败 {rank_type.value}: {e}")
            return []
    
    async def get_around_rank(
        self, 
        rank_type: RankType, 
        player_id: str, 
        range_size: int = 5,
        include_data: bool = True
    ) -> Dict[str, Any]:
        """
        获取玩家周围的排名
        
        Args:
            rank_type: 排行榜类型
            player_id: 玩家ID
            range_size: 范围大小（前后各几名）
            include_data: 是否包含玩家详细数据
            
        Returns:
            包含玩家排名和周围玩家的信息
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            # 获取玩家排名
            player_rank = await self.redis.client.zrevrank(rank_key, player_id)
            
            if player_rank is None:
                return {
                    "player_rank": None,
                    "player_score": None,
                    "around_players": []
                }
            
            # 获取玩家分数
            player_score = await self.redis.client.zscore(rank_key, player_id)
            
            # 计算范围
            start = max(0, player_rank - range_size)
            end = player_rank + range_size
            
            # 获取周围玩家
            around_players = await self.get_top_players(
                rank_type, start, end - start + 1, include_data
            )
            
            return {
                "player_rank": player_rank + 1,
                "player_score": int(player_score) if player_score else 0,
                "around_players": around_players
            }
            
        except Exception as e:
            logger.error(f"获取周围排名失败 {rank_type.value} {player_id}: {e}")
            return {
                "player_rank": None,
                "player_score": None,
                "around_players": []
            }
    
    async def remove_player(self, rank_type: RankType, player_id: str) -> bool:
        """
        从排行榜移除玩家
        
        Args:
            rank_type: 排行榜类型
            player_id: 玩家ID
            
        Returns:
            是否成功移除
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            # 移除玩家
            removed = await self.redis.client.zrem(rank_key, player_id)
            
            # 删除玩家详细数据
            data_key = f"{rank_key}:data:{player_id}"
            await self.redis.client.delete(data_key)
            
            if removed:
                logger.info(f"从排行榜移除玩家: {rank_type.value} {player_id}")
            
            return removed > 0
            
        except Exception as e:
            logger.error(f"移除玩家失败 {rank_type.value} {player_id}: {e}")
            return False
    
    async def create_snapshot(self, rank_type: RankType) -> bool:
        """
        创建排行榜快照
        
        Args:
            rank_type: 排行榜类型
            
        Returns:
            是否成功创建快照
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            snapshot_key = config["snapshot_key"]
            
            # 获取当前排行榜数据
            current_data = await self.redis.client.zrevrange(
                rank_key, 0, -1, withscores=True
            )
            
            if not current_data:
                return True
            
            # 清空旧快照
            await self.redis.client.delete(snapshot_key)
            
            # 创建新快照
            snapshot_dict = {player_id: score for player_id, score in current_data}
            await self.redis.client.zadd(snapshot_key, snapshot_dict)
            
            # 设置快照过期时间（7天）
            await self.redis.client.expire(snapshot_key, 604800)
            
            # 保存快照创建时间
            snapshot_time_key = f"{snapshot_key}:time"
            await self.redis.client.setex(
                snapshot_time_key, 604800, str(int(time.time()))
            )
            
            logger.info(f"创建排行榜快照: {rank_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"创建排行榜快照失败 {rank_type.value}: {e}")
            return False
    
    async def get_snapshot_data(
        self, 
        rank_type: RankType, 
        start: int = 0, 
        count: int = 10
    ) -> Tuple[List[Dict[str, Any]], Optional[datetime]]:
        """
        获取排行榜快照数据
        
        Args:
            rank_type: 排行榜类型
            start: 起始位置
            count: 数量
            
        Returns:
            (快照数据, 快照时间)
        """
        try:
            config = self.rank_configs[rank_type]
            snapshot_key = config["snapshot_key"]
            
            # 获取快照时间
            snapshot_time_key = f"{snapshot_key}:time"
            snapshot_time_str = await self.redis.client.get(snapshot_time_key)
            
            snapshot_time = None
            if snapshot_time_str:
                snapshot_time = datetime.fromtimestamp(int(snapshot_time_str))
            
            # 获取快照数据
            results = await self.redis.client.zrevrange(
                snapshot_key, start, start + count - 1, withscores=True
            )
            
            snapshot_data = []
            for i, (player_id, score) in enumerate(results):
                snapshot_data.append({
                    "rank": start + i + 1,
                    "player_id": player_id,
                    "score": int(score)
                })
            
            return snapshot_data, snapshot_time
            
        except Exception as e:
            logger.error(f"获取排行榜快照失败 {rank_type.value}: {e}")
            return [], None
    
    async def batch_update_ranks(
        self, 
        rank_type: RankType, 
        player_scores: Dict[str, float]
    ) -> bool:
        """
        批量更新排行榜
        
        Args:
            rank_type: 排行榜类型
            player_scores: 玩家分数字典
            
        Returns:
            是否成功更新
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            
            if not player_scores:
                return True
            
            # 批量更新
            await self.redis.client.zadd(rank_key, player_scores)
            
            # 保持排行榜大小
            max_size = config["max_size"]
            current_size = await self.redis.client.zcard(rank_key)
            
            if current_size > max_size:
                to_remove = current_size - max_size
                await self.redis.client.zremrangebyrank(rank_key, 0, to_remove - 1)
            
            logger.info(f"批量更新排行榜: {rank_type.value} 更新{len(player_scores)}个玩家")
            return True
            
        except Exception as e:
            logger.error(f"批量更新排行榜失败 {rank_type.value}: {e}")
            return False
    
    async def get_rank_stats(self, rank_type: RankType) -> Dict[str, Any]:
        """
        获取排行榜统计信息
        
        Args:
            rank_type: 排行榜类型
            
        Returns:
            统计信息
        """
        try:
            config = self.rank_configs[rank_type]
            rank_key = config["key"]
            snapshot_key = config["snapshot_key"]
            
            # 当前排行榜大小
            current_size = await self.redis.client.zcard(rank_key)
            
            # 快照大小
            snapshot_size = await self.redis.client.zcard(snapshot_key)
            
            # 最高分和最低分
            top_player = await self.redis.client.zrevrange(rank_key, 0, 0, withscores=True)
            bottom_player = await self.redis.client.zrange(rank_key, 0, 0, withscores=True)
            
            max_score = top_player[0][1] if top_player else 0
            min_score = bottom_player[0][1] if bottom_player else 0
            
            # 快照时间
            snapshot_time_key = f"{snapshot_key}:time"
            snapshot_time_str = await self.redis.client.get(snapshot_time_key)
            snapshot_time = None
            
            if snapshot_time_str:
                snapshot_time = datetime.fromtimestamp(int(snapshot_time_str)).isoformat()
            
            return {
                "rank_type": rank_type.value,
                "current_size": current_size,
                "max_size": config["max_size"],
                "snapshot_size": snapshot_size,
                "max_score": int(max_score),
                "min_score": int(min_score),
                "last_snapshot": snapshot_time
            }
            
        except Exception as e:
            logger.error(f"获取排行榜统计失败 {rank_type.value}: {e}")
            return {}
    
    # 便捷方法
    async def update_level_rank(
        self, 
        player_id: str, 
        level: int, 
        player_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新等级排行榜"""
        return await self.update_rank(RankType.LEVEL, player_id, float(level), player_data)
    
    async def update_power_rank(
        self, 
        player_id: str, 
        power: int, 
        player_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新战力排行榜"""
        return await self.update_rank(RankType.POWER, player_id, float(power), player_data)
    
    async def update_wealth_rank(
        self, 
        player_id: str, 
        wealth: int, 
        player_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新财富排行榜"""
        return await self.update_rank(RankType.WEALTH, player_id, float(wealth), player_data)