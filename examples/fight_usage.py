"""
战斗服务使用示例
Fight Service Usage Example

作者: lx
日期: 2025-06-18
描述: 演示如何使用战斗服务进行PVE和PVP战斗
"""
import asyncio
import json
import sys
from pathlib import Path

# 确保项目已正确安装或在PYTHONPATH中
from services.fight.handlers.battle_handler import (
    BattleHandler, BattleRequest, BattleType, PlayerData
)


async def pve_battle_example():
    """PVE战斗示例"""
    print("=== PVE战斗示例 ===")
    
    # 创建战斗处理器
    handler = BattleHandler()
    
    # 创建玩家数据
    player = PlayerData(
        player_id=1001,
        name="勇敢的冒险者",
        level=15,
        units=[
            {
                "id": 1,
                "name": "圣骑士",
                "hp": 180,
                "max_hp": 180,
                "atk": 85,
                "def": 50,
                "spd": 80,
                "skills": [1001, 1002],  # 普通攻击, 强力攻击
                "ai_type": "balanced"
            },
            {
                "id": 2,
                "name": "火焰法师",
                "hp": 120,
                "max_hp": 120,
                "atk": 130,
                "def": 25,
                "spd": 110,
                "skills": [1001, 1003],  # 普通攻击, 群体攻击
                "ai_type": "aggressive"
            }
        ],
        team_power=650
    )
    
    # 创建敌人数据
    enemy = PlayerData(
        player_id=9001,
        name="森林哥布林首领",
        level=12,
        units=[
            {
                "id": 101,
                "name": "哥布林首领",
                "hp": 220,
                "max_hp": 220,
                "atk": 75,
                "def": 40,
                "spd": 90,
                "skills": [1001, 1002],
                "ai_type": "aggressive"
            },
            {
                "id": 102,
                "name": "哥布林战士",
                "hp": 100,
                "max_hp": 100,
                "atk": 55,
                "def": 30,
                "spd": 85,
                "skills": [1001],
                "ai_type": "defensive"
            }
        ],
        team_power=480
    )
    
    # 创建战斗请求
    request = BattleRequest(
        battle_id="pve_example_001",
        battle_type=BattleType.PVE,
        attacker=player,
        defender=enemy,
        settings={
            "max_rounds": 25,
            "difficulty": "normal"
        }
    )
    
    # 执行战斗
    print("战斗开始...")
    report = await handler.process_battle(request)
    
    # 显示结果
    print(f"战斗结果: {'胜利' if report.winner == 1 else '失败' if report.winner == 2 else '平局'}")
    print(f"战斗回合数: {len(report.rounds)}")
    print(f"战斗时长: {report.duration:.3f}秒")
    
    if report.statistics:
        print("\n战斗统计:")
        for unit_id, damage in report.statistics.total_damage.items():
            print(f"  单位{unit_id} 造成伤害: {damage}")
        
        for unit_id, heal in report.statistics.total_heal.items():
            if heal > 0:
                print(f"  单位{unit_id} 治疗量: {heal}")
    
    print(f"\n奖励: 经验+{report.rewards.get('exp', 0)}, 金币+{report.rewards.get('gold', 0)}")
    
    return report


async def pvp_battle_example():
    """PVP战斗示例"""
    print("\n=== PVP战斗示例 ===")
    
    handler = BattleHandler()
    
    # 玩家1
    player1 = PlayerData(
        player_id=1001,
        name="暗影刺客",
        level=20,
        units=[
            {
                "id": 1,
                "name": "暗影刺客",
                "hp": 140,
                "max_hp": 140,
                "atk": 120,
                "def": 30,
                "spd": 150,
                "skills": [1001, 1002],
                "ai_type": "aggressive"
            }
        ],
        team_power=800
    )
    
    # 玩家2
    player2 = PlayerData(
        player_id=1002,
        name="钢铁守卫",
        level=20,
        units=[
            {
                "id": 2,
                "name": "钢铁守卫",
                "hp": 250,
                "max_hp": 250,
                "atk": 80,
                "def": 70,
                "spd": 60,
                "skills": [1001, 1002],
                "ai_type": "defensive"
            }
        ],
        team_power=750
    )
    
    # PVP战斗请求
    request = BattleRequest(
        battle_id="pvp_example_001",
        battle_type=BattleType.PVP,
        attacker=player1,
        defender=player2,
        settings={
            "max_rounds": 15,  # PVP回合数较少
            "arena_type": "ranked"
        }
    )
    
    print(f"{player1.name} VS {player2.name}")
    report = await handler.process_battle(request)
    
    print(f"胜者: {player1.name if report.winner == 1 else player2.name if report.winner == 2 else '平局'}")
    print(f"战斗回合数: {len(report.rounds)}")
    print(f"战斗时长: {report.duration:.3f}秒")
    
    return report


async def batch_battle_example():
    """批量战斗示例"""
    print("\n=== 批量战斗示例 ===")
    
    handler = BattleHandler()
    
    # 创建多个战斗请求
    requests = []
    for i in range(5):
        player = PlayerData(
            player_id=1000 + i,
            name=f"玩家{i+1}",
            level=10 + i,
            units=[
                {
                    "id": i * 10 + 1,
                    "name": f"战士{i+1}",
                    "hp": 100 + i * 10,
                    "max_hp": 100 + i * 10,
                    "atk": 50 + i * 5,
                    "def": 30 + i * 3,
                    "spd": 80 + i * 2,
                    "skills": [1001, 1002],
                    "ai_type": "balanced"
                }
            ],
            team_power=300 + i * 50
        )
        
        enemy = PlayerData(
            player_id=2000 + i,
            name=f"怪物{i+1}",
            level=8 + i,
            units=[
                {
                    "id": i * 10 + 2,
                    "name": f"哥布林{i+1}",
                    "hp": 80 + i * 8,
                    "max_hp": 80 + i * 8,
                    "atk": 40 + i * 4,
                    "def": 25 + i * 2,
                    "spd": 70 + i,
                    "skills": [1001],
                    "ai_type": "normal"
                }
            ],
            team_power=250 + i * 30
        )
        
        request = BattleRequest(
            battle_id=f"batch_battle_{i+1:03d}",
            battle_type=BattleType.PVE,
            attacker=player,
            defender=enemy
        )
        requests.append(request)
    
    # 批量处理
    print("开始批量处理5场战斗...")
    import time
    start_time = time.perf_counter()
    
    reports = await handler.batch_process_battles(requests)
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    # 统计结果
    victories = sum(1 for r in reports if r.winner == 1)
    defeats = sum(1 for r in reports if r.winner == 2)
    draws = sum(1 for r in reports if r.winner == 0)
    errors = sum(1 for r in reports if r.status.value == "error")
    
    print(f"批量战斗完成: {len(reports)}场战斗，耗时{total_time:.3f}秒")
    print(f"战斗结果: 胜利{victories}场，失败{defeats}场，平局{draws}场，错误{errors}场")
    print(f"平均每场战斗耗时: {total_time/len(reports)*1000:.2f}ms")
    
    return reports


async def performance_monitoring_example():
    """性能监控示例"""
    print("\n=== 性能监控示例 ===")
    
    handler = BattleHandler()
    
    # 执行一些战斗
    battle_tasks = []
    for i in range(10):
        request = BattleRequest(
            battle_id=f"perf_test_{i}",
            battle_type=BattleType.PVE,
            attacker=PlayerData(
                player_id=1000 + i,
                name=f"测试玩家{i}",
                level=10,
                units=[{
                    "id": i,
                    "name": "测试单位",
                    "hp": 100,
                    "max_hp": 100,
                    "atk": 50,
                    "def": 30,
                    "spd": 80,
                    "skills": [1001]
                }]
            ),
            defender=PlayerData(
                player_id=2000 + i,
                name=f"测试敌人{i}",
                level=8,
                units=[{
                    "id": 100 + i,
                    "name": "测试敌人",
                    "hp": 80,
                    "max_hp": 80,
                    "atk": 40,
                    "def": 25,
                    "spd": 70,
                    "skills": [1001]
                }]
            )
        )
        await handler.process_battle(request)
    
    # 获取统计信息
    stats = handler.get_stats()
    
    print("战斗服务统计信息:")
    print(f"  总战斗数: {stats['total_battles']}")
    print(f"  PVE战斗数: {stats['pve_battles']}")
    print(f"  PVP战斗数: {stats['pvp_battles']}")
    print(f"  平均战斗时间: {stats['avg_battle_time']:.3f}秒")
    print(f"  缓存命中数: {stats['cache_hits']}")
    print(f"  缓存未命中数: {stats['cache_misses']}")
    print(f"  错误次数: {stats['error_count']}")
    
    if 'cache_stats' in stats:
        cache_stats = stats['cache_stats']
        print(f"  缓存使用率: {cache_stats['cache_usage']:.1f}%")
    
    return stats


async def main():
    """主函数"""
    print("战斗服务使用示例")
    print("=" * 50)
    
    try:
        # PVE战斗示例
        await pve_battle_example()
        
        # PVP战斗示例
        await pvp_battle_example()
        
        # 批量战斗示例
        await batch_battle_example()
        
        # 性能监控示例
        await performance_monitoring_example()
        
        print("\n" + "=" * 50)
        print("所有示例运行完成!")
        
    except Exception as e:
        print(f"示例运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())