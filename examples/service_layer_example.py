"""
示例：Service层使用生成的Repository
展示业务逻辑与数据层的分离
作者: mrkingu
日期: 2025-06-20
"""
from typing import Dict, Any
from common.database.repositories.generated.player_repository import PlayerRepository

class PlayerService:
    """玩家服务层 - 包含所有业务逻辑"""
    
    def __init__(self, player_repository: PlayerRepository):
        """
        初始化玩家服务
        
        Args:
            player_repository: 玩家数据仓库
        """
        self.player_repository = player_repository
    
    async def recharge_diamond(self, player_id: str, amount: int, order_id: str) -> Dict[str, Any]:
        """
        充值钻石 - 业务逻辑在Service层
        
        Args:
            player_id: 玩家ID
            amount: 充值数量
            order_id: 订单ID
            
        Returns:
            充值结果
        """
        # 1. 业务验证
        if amount <= 0:
            return {"success": False, "reason": "invalid_amount"}
        
        if amount > 100000:  # 单次充值限制
            return {"success": False, "reason": "amount_limit_exceeded"}
        
        # 2. 验证订单（防重复充值）
        if await self._check_order_processed(order_id):
            return {"success": False, "reason": "order_already_processed"}
        
        # 3. 调用Repository（自动生成的并发安全方法）
        result = await self.player_repository.increment_diamond(
            entity_id=player_id,
            amount=amount,
            source="recharge",
            reason=f"充值订单:{order_id}"
        )
        
        if result.get("success"):
            # 4. 业务后处理
            await self._mark_order_processed(order_id)
            await self._send_recharge_notification(player_id, amount)
            await self._update_vip_experience(player_id, amount)
            
            # 5. 记录业务日志
            await self._log_recharge_event(player_id, amount, order_id)
        
        return result
    
    async def purchase_item(self, player_id: str, item_cost: int, item_name: str) -> Dict[str, Any]:
        """
        购买道具 - 扣除钻石的业务逻辑
        
        Args:
            player_id: 玩家ID
            item_cost: 道具价格
            item_name: 道具名称
            
        Returns:
            购买结果
        """
        # 1. 业务验证
        if item_cost <= 0:
            return {"success": False, "reason": "invalid_cost"}
        
        # 2. 检查玩家等级权限
        player = await self.player_repository.get_by_id(player_id)
        if not player:
            return {"success": False, "reason": "player_not_found"}
        
        if await self._check_item_level_requirement(player, item_name):
            return {"success": False, "reason": "level_requirement_not_met"}
        
        # 3. 调用Repository扣除钻石（自动包含余额检查）
        result = await self.player_repository.decrement_diamond(
            entity_id=player_id,
            amount=item_cost,
            source="purchase",
            reason=f"购买道具:{item_name}"
        )
        
        if result.get("success"):
            # 4. 业务后处理
            await self._add_item_to_inventory(player_id, item_name)
            await self._send_purchase_notification(player_id, item_name)
            
            # 5. 记录业务日志
            await self._log_purchase_event(player_id, item_cost, item_name)
        
        return result
    
    async def daily_energy_recovery(self, player_id: str) -> Dict[str, Any]:
        """
        每日体力回复 - 复杂的业务逻辑
        
        Args:
            player_id: 玩家ID
            
        Returns:
            回复结果
        """
        # 1. 获取玩家数据
        player = await self.player_repository.get_by_id(player_id)
        if not player:
            return {"success": False, "reason": "player_not_found"}
        
        # 2. 检查是否已经回复过
        if await self._check_energy_already_recovered_today(player_id):
            return {"success": False, "reason": "already_recovered_today"}
        
        # 3. 计算回复数量（业务规则）
        base_recovery = 100
        vip_bonus = self._calculate_vip_energy_bonus(player.get("vip_level", 0))
        total_recovery = base_recovery + vip_bonus
        
        # 4. 检查当前体力是否已满
        current_energy = player.get("energy", 0)
        max_energy = 999  # 体力上限
        
        if current_energy >= max_energy:
            return {"success": False, "reason": "energy_already_full"}
        
        # 5. 计算实际可回复数量
        actual_recovery = min(total_recovery, max_energy - current_energy)
        
        # 6. 调用Repository增加体力
        result = await self.player_repository.increment_energy(
            entity_id=player_id,
            amount=actual_recovery,
            source="daily_recovery",
            reason="每日体力回复"
        )
        
        if result.get("success"):
            # 7. 标记今日已回复
            await self._mark_energy_recovered_today(player_id)
            
            # 8. 发送通知
            await self._send_energy_recovery_notification(player_id, actual_recovery)
        
        return result
    
    # 私有方法 - 业务辅助逻辑
    async def _check_order_processed(self, order_id: str) -> bool:
        """检查订单是否已处理"""
        # 实现订单检查逻辑
        return False
    
    async def _mark_order_processed(self, order_id: str):
        """标记订单已处理"""
        # 实现订单标记逻辑
        pass
    
    async def _send_recharge_notification(self, player_id: str, amount: int):
        """发送充值通知"""
        # 实现通知发送逻辑
        pass
    
    async def _update_vip_experience(self, player_id: str, amount: int):
        """更新VIP经验"""
        # VIP经验增长业务逻辑
        pass
    
    async def _log_recharge_event(self, player_id: str, amount: int, order_id: str):
        """记录充值事件"""
        # 实现事件日志记录
        pass
    
    async def _check_item_level_requirement(self, player: Dict[str, Any], item_name: str) -> bool:
        """检查道具等级需求"""
        # 实现等级检查逻辑
        return False
    
    async def _add_item_to_inventory(self, player_id: str, item_name: str):
        """添加道具到背包"""
        # 实现背包逻辑
        pass
    
    async def _send_purchase_notification(self, player_id: str, item_name: str):
        """发送购买通知"""
        # 实现通知逻辑
        pass
    
    async def _log_purchase_event(self, player_id: str, cost: int, item_name: str):
        """记录购买事件"""
        # 实现事件日志
        pass
    
    async def _check_energy_already_recovered_today(self, player_id: str) -> bool:
        """检查今日是否已回复体力"""
        # 实现检查逻辑
        return False
    
    def _calculate_vip_energy_bonus(self, vip_level: int) -> int:
        """计算VIP体力加成"""
        # VIP加成计算逻辑
        return vip_level * 10
    
    async def _mark_energy_recovered_today(self, player_id: str):
        """标记今日体力已回复"""
        # 实现标记逻辑
        pass
    
    async def _send_energy_recovery_notification(self, player_id: str, amount: int):
        """发送体力回复通知"""
        # 实现通知逻辑
        pass


# 使用示例
async def example_usage():
    """使用示例"""
    # 模拟数据库客户端
    from unittest.mock import Mock
    
    redis_client = Mock()
    mongo_client = Mock()
    
    # 创建Repository（自动生成的）
    player_repo = PlayerRepository(redis_client, mongo_client)
    
    # 创建Service（包含业务逻辑）
    player_service = PlayerService(player_repo)
    
    # 业务操作调用
    result1 = await player_service.recharge_diamond(
        player_id="player_123",
        amount=1000,
        order_id="order_456"
    )
    
    result2 = await player_service.purchase_item(
        player_id="player_123", 
        item_cost=500,
        item_name="magical_sword"
    )
    
    result3 = await player_service.daily_energy_recovery(
        player_id="player_123"
    )
    
    return result1, result2, result3


if __name__ == "__main__":
    """
    这个示例展示了重构后的架构优势：
    
    1. **模型层纯净**: PlayerModel只包含数据字段定义和元数据
    2. **Repository层职责明确**: 只负责数据存取和并发安全操作
    3. **Service层包含业务逻辑**: 验证、计算、流程控制、通知等
    4. **自动生成减少重复代码**: increment_diamond等方法自动生成
    5. **并发安全**: Repository方法天然支持并发操作
    6. **易于测试**: 每层职责清晰，便于单元测试
    7. **易于扩展**: 新增模型时自动生成Repository，Service层专注业务
    """
    print("这是Service层使用示例，展示业务逻辑与数据层的分离")
    print("详细说明请查看源码注释")