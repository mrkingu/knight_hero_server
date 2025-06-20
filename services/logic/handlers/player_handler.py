"""
玩家处理器
Player Handler

作者: lx
日期: 2025-06-20
描述: 处理玩家相关请求：登录、信息查询、属性修改、离线处理
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from .base_handler import BaseHandler, handler
from ..services.player_service import PlayerService
from ..ranking.rank_service import RankService
from common.protocol.messages.auth.login_request import LoginRequest
from common.protocol.messages.auth.login_response import LoginResponse
from common.protocol.messages.player.player_info_request import PlayerInfoRequest
from common.protocol.messages.player.player_info_response import PlayerInfoResponse
from common.protocol.core.message_type import MessageType

logger = logging.getLogger(__name__)


class PlayerHandler(BaseHandler):
    """玩家相关请求处理器"""
    
    def __init__(self, player_service: Optional[PlayerService] = None, rank_service: Optional[RankService] = None):
        """初始化玩家处理器"""
        super().__init__()
        self.player_service = player_service or PlayerService()
        self.rank_service = rank_service or RankService()
        
        # 在线玩家缓存
        self.online_players: Dict[str, Dict[str, Any]] = {}
        
    @handler(cmd=MessageType.LOGIN_REQUEST)
    async def handle_login(self, req: LoginRequest) -> LoginResponse:
        """
        处理玩家登录
        
        Args:
            req: 登录请求
            
        Returns:
            LoginResponse: 登录响应
        """
        try:
            # 1. 验证登录信息
            if not await self._verify_login(req):
                response = LoginResponse()
                response.code = 401
                response.message = "登录验证失败"
                return response
            
            # 2. 生成玩家ID（这里简化处理，实际项目中应该有用户系统）
            player_id = f"player_{req.username}"
            
            # 3. 获取或创建玩家
            player = await self.player_service.get_or_create(
                player_id, 
                nickname=req.username
            )
            
            # 4. 更新登录信息
            login_result = await self.player_service.update_login_info(player_id)
            
            # 5. 恢复体力
            energy_result = await self.player_service.recover_energy(player_id)
            
            # 6. 更新排行榜
            player_data = await self.player_service.get_by_id(player_id)
            if player_data:
                # 更新等级排行榜
                await self.rank_service.update_level_rank(
                    player_id,
                    player_data.get("level", 1),
                    {
                        "nickname": player_data.get("nickname", ""),
                        "vip_level": player_data.get("vip_level", 0)
                    }
                )
                
                # 更新财富排行榜（金币+钻石）
                wealth = player_data.get("gold", 0) + player_data.get("diamond", 0) * 10
                await self.rank_service.update_wealth_rank(
                    player_id,
                    wealth,
                    {
                        "nickname": player_data.get("nickname", ""),
                        "gold": player_data.get("gold", 0),
                        "diamond": player_data.get("diamond", 0)
                    }
                )
            
            # 7. 添加到在线列表
            self.online_players[player_id] = {
                "login_time": datetime.now().isoformat(),
                "last_activity": time.time()
            }
            
            # 8. 返回登录响应
            response = LoginResponse()
            response.code = 0
            response.message = "登录成功"
            response.player_id = player_id
            response.token = f"token_{player_id}_{int(time.time())}"  # 简化的token
            response.server_time = int(time.time())
            response.player_info = player_data
            
            # 添加登录奖励信息
            if login_result.get("is_daily_first"):
                response.message += f"，获得每日登录奖励{login_result.get('login_reward', 0)}金币"
            
            logger.info(f"玩家登录成功: {player_id}")
            return response
            
        except Exception as e:
            logger.error(f"处理登录请求失败: {e}")
            response = LoginResponse()
            response.code = 500
            response.message = f"登录失败: {str(e)}"
            return response
    
    @handler(cmd=MessageType.PLAYER_INFO_REQUEST)
    async def handle_player_info(self, req: PlayerInfoRequest) -> PlayerInfoResponse:
        """
        处理玩家信息查询
        
        Args:
            req: 玩家信息请求
            
        Returns:
            PlayerInfoResponse: 玩家信息响应
        """
        try:
            # 获取目标玩家ID（如果为空则查询自己）
            target_player_id = req.target_player_id
            if not target_player_id:
                # 这里应该从请求上下文中获取当前玩家ID
                # 简化处理，假设请求中包含了player_id
                target_player_id = getattr(req, 'player_id', None)
            
            if not target_player_id:
                response = PlayerInfoResponse()
                response.code = 400
                response.message = "缺少玩家ID"
                return response
            
            # 获取玩家信息
            player_data = await self.player_service.get_by_id(target_player_id)
            if not player_data:
                response = PlayerInfoResponse()
                response.code = 404
                response.message = "玩家不存在"
                return response
            
            # 获取排行榜信息
            level_rank = await self.rank_service.get_rank(
                self.rank_service.RankType.LEVEL, target_player_id
            )
            wealth_rank = await self.rank_service.get_rank(
                self.rank_service.RankType.WEALTH, target_player_id
            )
            
            # 组装完整的玩家信息
            complete_info = dict(player_data)
            complete_info.update({
                "level_rank": level_rank,
                "wealth_rank": wealth_rank,
                "is_online": target_player_id in self.online_players
            })
            
            response = PlayerInfoResponse()
            response.code = 0
            response.message = "获取成功"
            response.player_info = complete_info
            
            logger.debug(f"获取玩家信息: {target_player_id}")
            return response
            
        except Exception as e:
            logger.error(f"处理玩家信息请求失败: {e}")
            response = PlayerInfoResponse()
            response.code = 500
            response.message = f"获取玩家信息失败: {str(e)}"
            return response
    
    @handler(cmd=MessageType.UPDATE_PLAYER_REQUEST)
    async def handle_update_player(self, req) -> Any:
        """
        处理玩家属性修改
        
        Args:
            req: 更新请求
            
        Returns:
            更新响应
        """
        try:
            # 从请求中提取参数（这里简化处理）
            player_id = getattr(req, 'player_id', None)
            updates = getattr(req, 'updates', {})
            
            if not player_id:
                from common.protocol.core.base_response import BaseResponse
                response = BaseResponse()
                response.MESSAGE_TYPE = MessageType.UPDATE_PLAYER_RESPONSE
                response.code = 400
                response.message = "缺少玩家ID"
                return response
            
            # 验证玩家是否存在
            player_data = await self.player_service.get_by_id(player_id)
            if not player_data:
                from common.protocol.core.base_response import BaseResponse
                response = BaseResponse()
                response.MESSAGE_TYPE = MessageType.UPDATE_PLAYER_RESPONSE
                response.code = 404
                response.message = "玩家不存在"
                return response
            
            # 验证更新字段（只允许更新某些字段）
            allowed_fields = {"nickname"}  # 只允许更新昵称
            invalid_fields = set(updates.keys()) - allowed_fields
            
            if invalid_fields:
                from common.protocol.core.base_response import BaseResponse
                response = BaseResponse()
                response.MESSAGE_TYPE = MessageType.UPDATE_PLAYER_RESPONSE
                response.code = 403
                response.message = f"不允许更新字段: {', '.join(invalid_fields)}"
                return response
            
            # 执行更新
            await self.player_service.update(player_id, updates)
            
            # 如果更新了昵称，同步更新排行榜数据
            if "nickname" in updates:
                current_data = await self.player_service.get_by_id(player_id)
                if current_data:
                    player_summary = {
                        "nickname": current_data.get("nickname", ""),
                        "vip_level": current_data.get("vip_level", 0)
                    }
                    
                    # 更新各个排行榜的玩家数据
                    await self.rank_service.update_level_rank(
                        player_id,
                        current_data.get("level", 1),
                        player_summary
                    )
            
            from common.protocol.core.base_response import BaseResponse
            response = BaseResponse()
            response.MESSAGE_TYPE = MessageType.UPDATE_PLAYER_RESPONSE
            response.code = 0
            response.message = "更新成功"
            
            logger.info(f"更新玩家信息: {player_id} {updates}")
            return response
            
        except Exception as e:
            logger.error(f"处理玩家更新请求失败: {e}")
            from common.protocol.core.base_response import BaseResponse
            response = BaseResponse()
            response.MESSAGE_TYPE = MessageType.UPDATE_PLAYER_RESPONSE
            response.code = 500
            response.message = f"更新失败: {str(e)}"
            return response
    
    async def handle_player_offline(self, player_id: str) -> None:
        """
        处理玩家离线
        
        Args:
            player_id: 玩家ID
        """
        try:
            # 设置玩家离线状态
            await self.player_service.set_offline(player_id)
            
            # 从在线列表移除
            if player_id in self.online_players:
                online_time = time.time() - self.online_players[player_id].get("last_activity", time.time())
                del self.online_players[player_id]
                logger.info(f"玩家离线: {player_id} 在线时长: {online_time:.0f}秒")
            
        except Exception as e:
            logger.error(f"处理玩家离线失败 {player_id}: {e}")
    
    async def _verify_login(self, req: LoginRequest) -> bool:
        """
        验证登录信息
        
        Args:
            req: 登录请求
            
        Returns:
            是否验证通过
        """
        try:
            # 基本验证
            if not req.validate():
                return False
            
            # 这里可以添加更多验证逻辑：
            # - 检查用户名密码
            # - 验证设备ID
            # - 检查版本兼容性
            # - 防止重复登录等
            
            # 简化处理，只检查基本字段
            if len(req.username) < 3 or len(req.username) > 20:
                return False
            
            if not req.password:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证登录信息失败: {e}")
            return False
    
    def get_online_players(self) -> Dict[str, Dict[str, Any]]:
        """
        获取在线玩家列表
        
        Returns:
            在线玩家字典
        """
        return self.online_players.copy()
    
    def get_online_count(self) -> int:
        """
        获取在线玩家数量
        
        Returns:
            在线玩家数量
        """
        return len(self.online_players)
    
    async def update_player_activity(self, player_id: str) -> None:
        """
        更新玩家活跃时间
        
        Args:
            player_id: 玩家ID
        """
        if player_id in self.online_players:
            self.online_players[player_id]["last_activity"] = time.time()
    
    async def cleanup_inactive_players(self, timeout_seconds: int = 1800) -> int:
        """
        清理不活跃的玩家
        
        Args:
            timeout_seconds: 超时时间（秒）
            
        Returns:
            清理的玩家数量
        """
        current_time = time.time()
        inactive_players = []
        
        for player_id, info in self.online_players.items():
            last_activity = info.get("last_activity", current_time)
            if current_time - last_activity > timeout_seconds:
                inactive_players.append(player_id)
        
        # 批量处理离线
        for player_id in inactive_players:
            await self.handle_player_offline(player_id)
        
        if inactive_players:
            logger.info(f"清理不活跃玩家: {len(inactive_players)}个")
        
        return len(inactive_players)