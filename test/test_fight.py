"""
战斗服务测试
Fight Service Tests

作者: lx
日期: 2025-06-18
描述: 战斗服务的单元测试和集成测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
import time
from typing import List, Dict, Any

from services.fight.core.battle_unit import (
    BattleUnit, BattleAttributes, Buff, BuffSystem, BuffEffect, BuffType, UnitState
)
from services.fight.core.battle_engine import (
    BattleEngine, BattleContext, SkillConfig, SkillType, TargetType, DamageType
)
from services.fight.handlers.battle_handler import (
    BattleHandler, BattleRequest, BattleType, PlayerData
)
from services.fight.utils.object_pool import ObjectPool, get_pool_manager


class TestBattleUnit:
    """测试战斗单位"""
    
    def test_battle_unit_creation(self):
        """测试战斗单位创建"""
        attributes = BattleAttributes(hp=100, atk=50, def_=30, spd=80)
        unit = BattleUnit(
            unit_id=1,
            name="测试单位",
            attributes=attributes
        )
        
        assert unit.id == 1
        assert unit.name == "测试单位"
        assert unit.is_alive()
        assert unit.can_act()
        assert unit.current_attributes.hp == 100
    
    def test_battle_unit_damage(self):
        """测试战斗单位受伤"""
        unit = BattleUnit(1, "测试单位")
        
        # 受到伤害
        damage = unit.take_damage(30)
        assert damage == 30
        assert unit.current_attributes.hp == 70
        assert unit.is_alive()
        
        # 受到致命伤害
        damage = unit.take_damage(100)
        assert damage == 70  # 只能造成剩余血量的伤害
        assert unit.current_attributes.hp == 0
        assert unit.is_dead()
        assert unit.state == UnitState.DEAD
    
    def test_battle_unit_heal(self):
        """测试战斗单位治疗"""
        unit = BattleUnit(1, "测试单位")
        unit.take_damage(50)
        
        # 治疗
        heal = unit.heal(30)
        assert heal == 30
        assert unit.current_attributes.hp == 80
        
        # 过量治疗
        heal = unit.heal(50)
        assert heal == 20  # 只能治疗到满血
        assert unit.current_attributes.hp == 100
    
    def test_buff_system(self):
        """测试Buff系统"""
        unit = BattleUnit(1, "测试单位")
        
        # 添加攻击力Buff
        atk_buff = Buff(
            id=1001,
            name="攻击力提升",
            buff_type=BuffType.POSITIVE,
            effect=BuffEffect.ATK_BOOST,
            value=20,
            duration=3,
            remaining_turns=3
        )
        
        original_atk = unit.current_attributes.atk
        unit.add_buff(atk_buff)
        
        assert unit.current_attributes.atk == original_atk + 20
        assert len(unit.buff_system.buffs) == 1
        
        # 更新回合，Buff持续时间减少
        unit.update_turn()
        assert unit.buff_system.buffs[1001].remaining_turns == 2
        
        # Buff过期
        unit.buff_system.buffs[1001].remaining_turns = 1
        unit.update_turn()
        assert len(unit.buff_system.buffs) == 0
        assert unit.current_attributes.atk == original_atk


class TestObjectPool:
    """测试对象池"""
    
    def test_object_pool_basic(self):
        """测试对象池基本功能"""
        pool = ObjectPool(dict, size=5)
        
        # 获取对象
        obj1 = pool.get()
        obj2 = pool.get()
        assert isinstance(obj1, dict)
        assert isinstance(obj2, dict)
        assert obj1 is not obj2
        
        # 归还对象
        assert pool.put(obj1)
        assert pool.put(obj2)
        
        # 再次获取应该复用
        obj3 = pool.get()
        assert obj3 in [obj1, obj2]  # 应该是之前的对象之一
    
    def test_object_pool_stats(self):
        """测试对象池统计"""
        pool = ObjectPool(list, size=3, auto_cleanup=False)  # 使用不同的类型避免冲突
        
        # 获取初始统计
        initial_stats = pool.get_stats()
        initial_created = initial_stats["objects_created"]
        initial_reused = initial_stats["objects_reused"]
        
        # 获取一些对象
        obj1 = pool.get()
        obj2 = pool.get()
        
        stats = pool.get_stats()
        created_after = stats["objects_created"]
        assert created_after >= initial_created + 2  # 至少创建了2个新对象
        
        # 归还并重新获取
        pool.put(obj1)
        obj3 = pool.get()
        
        stats = pool.get_stats()
        assert stats["objects_reused"] >= initial_reused + 1  # 至少复用了1个对象


class TestBattleEngine:
    """测试战斗引擎"""
    
    def create_test_units(self) -> List[BattleUnit]:
        """创建测试单位"""
        units = []
        
        # 攻击方
        attacker = BattleUnit(
            unit_id=1,
            name="攻击者",
            attributes=BattleAttributes(hp=100, atk=60, def_=20, spd=100)
        )
        attacker.team_id = 1
        attacker.skills = [1001, 1002]  # 普通攻击, 强力攻击
        units.append(attacker)
        
        # 防守方
        defender = BattleUnit(
            unit_id=2,
            name="防守者",
            attributes=BattleAttributes(hp=80, atk=40, def_=30, spd=80)
        )
        defender.team_id = 2
        defender.skills = [1001]  # 普通攻击
        units.append(defender)
        
        return units
    
    @pytest.mark.asyncio
    async def test_battle_engine_calculation(self):
        """测试战斗引擎计算"""
        engine = BattleEngine()
        units = self.create_test_units()
        
        context = BattleContext(
            battle_id="test_battle",
            attacker_team=[units[0]],
            defender_team=[units[1]],
            max_rounds=10
        )
        
        rounds_data = await engine.calculate_battle(context)
        
        assert len(rounds_data) > 0
        assert context.is_finished
        assert context.winner in [1, 2]  # 有一方获胜
        
        # 检查战斗统计
        assert context.total_damage
        
        # 检查回合数据
        for round_data in rounds_data:
            assert round_data.round_number > 0
            assert isinstance(round_data.actions, list)


@pytest.mark.asyncio
class TestBattleHandler:
    """测试战斗处理器"""
    
    async def test_pve_battle(self):
        """测试PVE战斗"""
        handler = BattleHandler()
        
        # 创建战斗请求
        request = BattleRequest(
            battle_id="test_pve_001",
            battle_type=BattleType.PVE,
            attacker=PlayerData(
                player_id=1001,
                name="玩家1",
                level=10,
                units=[
                    {
                        "id": 1,
                        "name": "战士",
                        "hp": 120,
                        "max_hp": 120,
                        "atk": 70,
                        "def": 35,
                        "spd": 90,
                        "skills": [1001, 1002]
                    }
                ]
            ),
            defender=PlayerData(
                player_id=2001,
                name="怪物",
                level=8,
                units=[
                    {
                        "id": 2,
                        "name": "哥布林",
                        "hp": 80,
                        "max_hp": 80,
                        "atk": 45,
                        "def": 25,
                        "spd": 70,
                        "skills": [1001]
                    }
                ]
            )
        )
        
        # 处理战斗
        report = await handler.process_battle(request)
        
        assert report.battle_id == "test_pve_001"
        assert report.battle_type == BattleType.PVE
        assert report.status.value in ["finished", "error"]
        
        if report.status.value == "finished":
            assert report.winner is not None
            assert len(report.rounds) > 0
            assert report.statistics is not None
            assert report.rewards
    
    async def test_pvp_battle(self):
        """测试PVP战斗"""
        handler = BattleHandler()
        
        # 创建PVP战斗请求
        request = BattleRequest(
            battle_id="test_pvp_001",
            battle_type=BattleType.PVP,
            attacker=PlayerData(
                player_id=1001,
                name="玩家1",
                level=15,
                units=[
                    {
                        "id": 1,
                        "name": "法师",
                        "hp": 90,
                        "max_hp": 90,
                        "atk": 85,
                        "def": 20,
                        "spd": 110,
                        "skills": [1001, 1003]
                    }
                ]
            ),
            defender=PlayerData(
                player_id=1002,
                name="玩家2",
                level=14,
                units=[
                    {
                        "id": 2,
                        "name": "盗贼",
                        "hp": 75,
                        "max_hp": 75,
                        "atk": 90,
                        "def": 15,
                        "spd": 130,
                        "skills": [1001, 1002]
                    }
                ]
            )
        )
        
        # 处理战斗
        report = await handler.process_battle(request)
        
        assert report.battle_type == BattleType.PVP
        
        if report.status.value == "finished":
            # PVP战斗奖励应该更高
            print(f"PVP战斗奖励: {report.rewards}")
            assert report.rewards["exp"] > 0  # 应该有经验奖励
    
    async def test_batch_battles(self):
        """测试批量战斗处理"""
        handler = BattleHandler()
        
        # 创建多个战斗请求
        requests = []
        for i in range(3):
            request = BattleRequest(
                battle_id=f"batch_test_{i}",
                battle_type=BattleType.PVE,
                attacker=PlayerData(
                    player_id=1000 + i,
                    name=f"玩家{i}",
                    level=10,
                    units=[
                        {
                            "id": i * 10 + 1,
                            "name": "单位",
                            "hp": 100,
                            "max_hp": 100,
                            "atk": 50,
                            "def": 30,
                            "spd": 80,
                            "skills": [1001]
                        }
                    ]
                ),
                defender=PlayerData(
                    player_id=2000 + i,
                    name=f"敌人{i}",
                    level=8,
                    units=[
                        {
                            "id": i * 10 + 2,
                            "name": "敌人",
                            "hp": 70,
                            "max_hp": 70,
                            "atk": 40,
                            "def": 25,
                            "spd": 60,
                            "skills": [1001]
                        }
                    ]
                )
            )
            requests.append(request)
        
        # 批量处理
        reports = await handler.batch_process_battles(requests)
        
        assert len(reports) == 3
        for report in reports:
            assert report.battle_id.startswith("batch_test_")
    
    async def test_battle_cache(self):
        """测试战斗缓存"""
        handler = BattleHandler()
        
        request = BattleRequest(
            battle_id="cache_test_001",
            battle_type=BattleType.PVE,
            attacker=PlayerData(
                player_id=1001,
                name="玩家",
                level=10,
                units=[{"id": 1, "name": "单位", "skills": [1001]}]
            ),
            defender=PlayerData(
                player_id=2001,
                name="敌人",
                level=8,
                units=[{"id": 2, "name": "敌人", "skills": [1001]}]
            )
        )
        
        # 第一次处理
        start_time = time.perf_counter()
        report1 = await handler.process_battle(request)
        first_time = time.perf_counter() - start_time
        
        # 第二次处理（应该从缓存获取）
        start_time = time.perf_counter()
        report2 = await handler.process_battle(request)
        second_time = time.perf_counter() - start_time
        
        # 验证缓存效果
        assert report1.battle_id == report2.battle_id
        assert second_time < first_time  # 缓存应该更快
        
        # 检查统计信息
        stats = handler.get_stats()
        assert stats["cache_hits"] > 0


class TestPerformance:
    """性能测试"""
    
    @pytest.mark.asyncio
    async def test_high_volume_battles(self):
        """测试高容量战斗处理"""
        handler = BattleHandler()
        
        # 创建多个战斗请求
        requests = []
        battle_count = 100  # 测试100场战斗
        
        for i in range(battle_count):
            request = BattleRequest(
                battle_id=f"perf_test_{i}",
                battle_type=BattleType.PVE,
                attacker=PlayerData(
                    player_id=1000 + i,
                    name=f"玩家{i}",
                    level=10,
                    units=[
                        {
                            "id": i * 10 + 1,
                            "name": "单位",
                            "hp": 100 + i,
                            "max_hp": 100 + i,
                            "atk": 50 + i % 20,
                            "def": 30 + i % 15,
                            "spd": 80 + i % 30,
                            "skills": [1001, 1002]
                        }
                    ]
                ),
                defender=PlayerData(
                    player_id=2000 + i,
                    name=f"敌人{i}",
                    level=8,
                    units=[
                        {
                            "id": i * 10 + 2,
                            "name": "敌人",
                            "hp": 80 + i % 20,
                            "max_hp": 80 + i % 20,
                            "atk": 40 + i % 15,
                            "def": 25 + i % 10,
                            "spd": 70 + i % 20,
                            "skills": [1001]
                        }
                    ]
                )
            )
            requests.append(request)
        
        # 批量处理并计时
        start_time = time.perf_counter()
        reports = await handler.batch_process_battles(requests)
        total_time = time.perf_counter() - start_time
        
        # 验证结果
        assert len(reports) == battle_count
        successful_battles = sum(1 for r in reports if r.status.value == "finished")
        
        print(f"处理 {battle_count} 场战斗，成功 {successful_battles} 场，耗时 {total_time:.2f} 秒")
        print(f"平均每场战斗耗时: {total_time / battle_count * 1000:.2f} ms")
        
        # 性能要求：平均每场战斗应在50ms以内完成
        avg_time_per_battle = total_time / battle_count
        assert avg_time_per_battle < 0.05  # 50ms
        
        # 成功率应该很高
        success_rate = successful_battles / battle_count
        assert success_rate > 0.95  # 95%以上成功率


def test_import_and_basic_functionality():
    """测试基本导入和功能"""
    try:
        from services.fight import (
            BattleUnit, BattleEngine, BattleHandler, ObjectPool
        )
        
        # 基本功能测试
        unit = BattleUnit(1, "测试")
        assert unit.is_alive()
        
        engine = BattleEngine()
        assert engine.skill_configs
        
        handler = BattleHandler()
        stats = handler.get_stats()
        assert "total_battles" in stats
        
        pool = ObjectPool(dict, size=10)
        obj = pool.get()
        assert isinstance(obj, dict)
        
        print("✅ 基本导入和功能测试通过")
        
    except Exception as e:
        pytest.fail(f"基本功能测试失败: {e}")


if __name__ == "__main__":
    # 运行基本测试
    test_import_and_basic_functionality()
    
    # 运行异步测试
    async def run_async_tests():
        print("开始异步测试...")
        
        # 战斗单位测试
        unit_test = TestBattleUnit()
        unit_test.test_battle_unit_creation()
        unit_test.test_battle_unit_damage()
        unit_test.test_battle_unit_heal()
        unit_test.test_buff_system()
        print("✅ 战斗单位测试通过")
        
        # 对象池测试
        pool_test = TestObjectPool()
        pool_test.test_object_pool_basic()
        pool_test.test_object_pool_stats()
        print("✅ 对象池测试通过")
        
        # 战斗引擎测试
        engine_test = TestBattleEngine()
        await engine_test.test_battle_engine_calculation()
        print("✅ 战斗引擎测试通过")
        
        # 战斗处理器测试
        handler_test = TestBattleHandler()
        await handler_test.test_pve_battle()
        await handler_test.test_pvp_battle()
        await handler_test.test_batch_battles()
        await handler_test.test_battle_cache()
        print("✅ 战斗处理器测试通过")
        
        # 性能测试
        perf_test = TestPerformance()
        await perf_test.test_high_volume_battles()
        print("✅ 性能测试通过")
        
        print("🎉 所有测试通过！")
    
    asyncio.run(run_async_tests())