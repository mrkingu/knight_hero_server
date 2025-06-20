"""
测试自动生成的Repository
作者: mrkingu
日期: 2025-06-20
"""
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.mark.asyncio
async def test_generated_player_repository():
    """测试自动生成的玩家Repository"""
    from common.database.repositories.generated.player_repository import PlayerRepository
    
    # Mock Redis和MongoDB客户端
    redis_client = Mock()
    mongo_client = Mock()
    
    # 创建Repository实例
    repo = PlayerRepository(redis_client, mongo_client)
    
    # 测试并发字段配置
    concurrent_fields = repo.get_concurrent_fields()
    
    assert "diamond" in concurrent_fields
    assert "gold" in concurrent_fields
    assert "exp" in concurrent_fields
    assert "energy" in concurrent_fields
    
    # 检查字段配置
    diamond_config = concurrent_fields["diamond"]
    assert diamond_config["type"] == "number"
    assert "incr" in diamond_config["operations"]
    assert "decr" in diamond_config["operations"]
    assert diamond_config["min"] == 0
    assert diamond_config["max"] == 999999999

@pytest.mark.asyncio
async def test_generated_guild_repository():
    """测试自动生成的公会Repository"""
    from common.database.repositories.generated.guild_repository import GuildRepository
    
    # Mock Redis和MongoDB客户端
    redis_client = Mock()
    mongo_client = Mock()
    
    # 创建Repository实例
    repo = GuildRepository(redis_client, mongo_client)
    
    # 测试并发字段配置
    concurrent_fields = repo.get_concurrent_fields()
    
    assert "exp" in concurrent_fields
    
    # 检查字段配置
    exp_config = concurrent_fields["exp"]
    assert exp_config["type"] == "number"
    assert "incr" in exp_config["operations"]

@pytest.mark.asyncio
async def test_generated_item_repository():
    """测试自动生成的道具Repository"""
    from common.database.repositories.generated.item_repository import ItemRepository
    
    # Mock Redis和MongoDB客户端
    redis_client = Mock()
    mongo_client = Mock()
    
    # 创建Repository实例
    repo = ItemRepository(redis_client, mongo_client)
    
    # 测试并发字段配置 (ItemModel没有定义concurrent_fields，应该为空)
    concurrent_fields = repo.get_concurrent_fields()
    
    assert isinstance(concurrent_fields, dict)

def test_repository_generation_structure():
    """测试Repository生成的结构"""
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    generated_path = project_root / "common" / "database" / "repositories" / "generated"
    
    # 检查生成的文件是否存在
    assert (generated_path / "player_repository.py").exists()
    assert (generated_path / "guild_repository.py").exists() 
    assert (generated_path / "item_repository.py").exists()
    assert (generated_path / "__init__.py").exists()
    
    # 检查自定义目录是否存在
    custom_path = project_root / "common" / "database" / "repositories" / "custom"
    assert custom_path.exists()
    assert (custom_path / "__init__.py").exists()

if __name__ == "__main__":
    import asyncio
    
    print("Running generated repository tests...")
    
    # 运行异步测试
    asyncio.run(test_generated_player_repository())
    asyncio.run(test_generated_guild_repository())
    asyncio.run(test_generated_item_repository())
    
    # 运行同步测试
    test_repository_generation_structure()
    
    print("✅ All generated repository tests passed!")