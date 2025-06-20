"""
配置系统测试模块
Configuration System Test Module

作者: lx
日期: 2025-06-18
描述: 配置管理系统的单元测试和集成测试
"""

import pytest
import asyncio
import json
import pandas as pd
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from common.config.base_config import (
    BaseConfig, ItemConfig, SkillConfig, NpcConfig, 
    ConfigManager, get_config_manager
)
from common.config.excel_to_json import ExcelToJsonConverter, create_sample_excel_files
from common.config.config_gen import ConfigClassGenerator
from common.config.config_loader import ConfigLoader, initialize_configs


class TestBaseConfig:
    """基础配置类测试"""
    
    def test_item_config_creation(self):
        """测试道具配置创建"""
        item_data = {
            "item_id": 1001,
            "name": "小血瓶",
            "type": 1,
            "quality": 2,
            "price": 100,
            "description": "恢复100点生命值",
            "max_stack": 10,
            "level_requirement": 1
        }
        
        item = ItemConfig(**item_data)
        assert item.item_id == 1001
        assert item.name == "小血瓶"
        assert item.quality == 2
        assert item.max_stack == 10
        
    def test_item_config_validation(self):
        """测试道具配置验证"""
        # 测试品质范围验证
        with pytest.raises(ValueError):
            ItemConfig(
                item_id=1001,
                name="测试道具",
                type=1,
                quality=6,  # 超出范围
                price=100,
                description="测试"
            )
            
        # 测试价格验证
        with pytest.raises(ValueError):
            ItemConfig(
                item_id=1001,
                name="测试道具",
                type=1,
                quality=1,
                price=-10,  # 负数价格
                description="测试"
            )
    
    def test_skill_config_creation(self):
        """测试技能配置创建"""
        skill_data = {
            "skill_id": 2001,
            "name": "火球术",
            "type": 1,
            "level": 1,
            "damage": 100,
            "mana_cost": 50,
            "cooldown": 3.0,
            "description": "发射火球攻击敌人"
        }
        
        skill = SkillConfig(**skill_data)
        assert skill.skill_id == 2001
        assert skill.name == "火球术"
        assert skill.damage == 100
        assert skill.cooldown == 3.0
    
    def test_npc_config_creation(self):
        """测试NPC配置创建"""
        npc_data = {
            "npc_id": 3001,
            "name": "哥布林",
            "level": 5,
            "hp": 500,
            "attack": 80,
            "defense": 20,
            "drop_items": [1001, 1002],
            "ai_type": "aggressive"
        }
        
        npc = NpcConfig(**npc_data)
        assert npc.npc_id == 3001
        assert npc.name == "哥布林"
        assert npc.drop_items == [1001, 1002]
        assert npc.ai_type == "aggressive"


class TestConfigManager:
    """配置管理器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.manager = ConfigManager()
        
        # 添加测试数据
        self.manager.item_config[1001] = ItemConfig(
            item_id=1001,
            name="小血瓶",
            type=1,
            quality=1,
            price=100,
            description="恢复100点生命值"
        )
        
        self.manager.skill_config[2001] = SkillConfig(
            skill_id=2001,
            name="火球术",
            type=1,
            level=1,
            damage=100,
            mana_cost=50,
            cooldown=3.0,
            description="发射火球攻击敌人"
        )
    
    def test_get_item(self):
        """测试获取道具配置"""
        item = self.manager.get_item(1001)
        assert item is not None
        assert item.name == "小血瓶"
        
        # 测试不存在的道具
        non_existent = self.manager.get_item(9999)
        assert non_existent is None
    
    def test_get_skill(self):
        """测试获取技能配置"""
        skill = self.manager.get_skill(2001)
        assert skill is not None
        assert skill.name == "火球术"
    
    def test_get_items_by_type(self):
        """测试按类型获取道具"""
        # 添加更多测试数据
        self.manager.item_config[1002] = ItemConfig(
            item_id=1002,
            name="大血瓶",
            type=1,
            quality=2,
            price=200,
            description="恢复300点生命值"
        )
        
        type_1_items = self.manager.get_items_by_type(1)
        assert len(type_1_items) == 2
        assert all(item.type == 1 for item in type_1_items)
    
    def test_config_count(self):
        """测试配置数量统计"""
        stats = self.manager.get_config_count()
        assert stats["items"] == 1
        assert stats["skills"] == 1
        assert stats["npcs"] == 0
        assert stats["total"] == 2
    
    def test_validate_configs(self):
        """测试配置验证"""
        errors = self.manager.validate_all_configs()
        assert isinstance(errors, dict)
        assert "items" in errors
        assert "skills" in errors
        assert "npcs" in errors
    
    def test_clear_all(self):
        """测试清空所有配置"""
        self.manager.clear_all()
        stats = self.manager.get_config_count()
        assert stats["total"] == 0


class TestExcelToJsonConverter:
    """Excel转JSON转换器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.excel_dir = Path(self.temp_dir) / "excel"
        self.json_dir = Path(self.temp_dir) / "json"
        
        self.converter = ExcelToJsonConverter(
            excel_dir=str(self.excel_dir),
            json_dir=str(self.json_dir)
        )
    
    def teardown_method(self):
        """测试后清理"""
        shutil.rmtree(self.temp_dir)
    
    def test_scan_excel_files(self):
        """测试扫描Excel文件"""
        # 创建测试Excel文件
        self.excel_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建空的Excel文件用于测试
        test_file = self.excel_dir / "test.xlsx"
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        df.to_excel(test_file, index=False)
        
        files = self.converter.scan_excel_files()
        assert len(files) == 1
        assert files[0].name == "test.xlsx"
    
    def test_create_sample_excel_files(self):
        """测试创建示例Excel文件"""
        create_sample_excel_files(str(self.excel_dir))
        
        excel_files = list(self.excel_dir.glob("*.xlsx"))
        assert len(excel_files) >= 1
        
        # 检查item.xlsx文件是否存在
        item_file = self.excel_dir / "item.xlsx"
        assert item_file.exists()
    
    def test_convert_value(self):
        """测试值类型转换"""
        # 测试整数转换
        result = self.converter._convert_value("123", "int")
        assert result == 123
        assert isinstance(result, int)
        
        # 测试浮点数转换
        result = self.converter._convert_value("123.45", "float")
        assert result == 123.45
        assert isinstance(result, float)
        
        # 测试布尔值转换
        result = self.converter._convert_value("true", "bool")
        assert result is True
        
        result = self.converter._convert_value("false", "bool")
        assert result is False
        
        # 测试列表转换
        result = self.converter._convert_value("1,2,3", "list")
        assert result == ["1", "2", "3"]
    
    def test_batch_convert(self):
        """测试批量转换"""
        # 创建示例Excel文件
        create_sample_excel_files(str(self.excel_dir))
        
        # 执行批量转换
        results = self.converter.batch_convert()
        
        # 检查转换结果
        assert len(results) >= 1
        assert any(results.values())  # 至少有一个文件转换成功
        
        # 检查生成的JSON文件
        json_files = list(self.json_dir.glob("*.json"))
        assert len(json_files) >= 1


class TestConfigClassGenerator:
    """配置类生成器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.json_dir = Path(self.temp_dir) / "json"
        self.output_dir = Path(self.temp_dir) / "generated"
        
        self.generator = ConfigClassGenerator(
            json_dir=str(self.json_dir),
            output_dir=str(self.output_dir)
        )
        
        # 创建测试JSON文件
        self.json_dir.mkdir(parents=True, exist_ok=True)
        
        test_data = {
            "1001": {
                "item_id": 1001,
                "name": "小血瓶",
                "type": 1,
                "quality": 2,
                "price": 100,
                "description": "恢复100点生命值"
            }
        }
        
        test_file = self.json_dir / "item.json"
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=2)
    
    def teardown_method(self):
        """测试后清理"""
        shutil.rmtree(self.temp_dir)
    
    def test_scan_json_files(self):
        """测试扫描JSON文件"""
        files = self.generator.scan_json_files()
        assert len(files) == 1
        assert files[0].name == "item.json"
    
    def test_analyze_json_structure(self):
        """测试分析JSON结构"""
        json_file = self.json_dir / "item.json"
        structure = self.generator.analyze_json_structure(json_file)
        
        assert structure["file_name"] == "item"
        assert structure["record_count"] == 1
        assert "field_types" in structure
        assert "item_id" in structure["field_types"]
    
    def test_infer_field_type(self):
        """测试字段类型推断"""
        # 测试特殊字段名推断
        field_type = self.generator._infer_field_type("item_id", 1001, {})
        assert field_type == "int"
        
        field_type = self.generator._infer_field_type("name", "测试", {})
        assert field_type == "str"
        
        field_type = self.generator._infer_field_type("price", 100, {})
        assert field_type == "int"
    
    def test_to_pascal_case(self):
        """测试下划线转帕斯卡命名"""
        result = self.generator._to_pascal_case("item_config")
        assert result == "ItemConfig"
        
        result = self.generator._to_pascal_case("npc")
        assert result == "Npc"
    
    def test_generate_all_configs(self):
        """测试生成所有配置类"""
        results = self.generator.generate_all_configs()
        
        # 检查生成结果
        assert len(results) >= 1
        assert any(results.values())  # 至少有一个文件生成成功
        
        # 检查生成的文件
        output_files = list(self.output_dir.glob("*.py"))
        assert len(output_files) >= 1


class TestConfigLoader:
    """配置加载器测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / "json"
        
        # 创建测试配置文件
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建道具配置
        item_data = {
            "1001": {
                "item_id": 1001,
                "name": "小血瓶",
                "type": 1,
                "quality": 1,
                "price": 100,
                "description": "恢复100点生命值",
                "max_stack": 10,
                "level_requirement": 1
            }
        }
        
        item_file = self.config_dir / "item.json"
        with open(item_file, 'w', encoding='utf-8') as f:
            json.dump(item_data, f, ensure_ascii=False, indent=2)
        
        self.loader = ConfigLoader(config_dir=str(self.config_dir))
    
    def teardown_method(self):
        """测试后清理"""
        shutil.rmtree(self.temp_dir)
    
    def test_scan_config_files(self):
        """测试扫描配置文件"""
        files = self.loader._scan_config_files()
        assert len(files) == 1
        assert files[0].name == "item.json"
    
    @pytest.mark.asyncio
    async def test_load_all_configs(self):
        """测试加载所有配置"""
        success = await self.loader.load_all_configs()
        assert success
        assert self.loader.is_loaded()
        
        # 检查配置是否正确加载
        manager = self.loader.config_manager
        stats = manager.get_config_count()
        assert stats["items"] == 1
        
        item = manager.get_item(1001)
        assert item is not None
        assert item.name == "小血瓶"
    
    @pytest.mark.asyncio
    async def test_load_item_configs(self):
        """测试加载道具配置"""
        test_data = {
            "1001": {
                "item_id": 1001,
                "name": "测试道具",
                "type": 1,
                "quality": 1,
                "price": 100,
                "description": "测试描述"
            }
        }
        
        config_file = self.config_dir / "test_item.json"
        success = await self.loader._load_item_configs(test_data, config_file)
        assert success
        
        # 检查是否正确加载
        item = self.loader.config_manager.get_item(1001)
        assert item is not None
        assert item.name == "测试道具"
    
    def test_get_config_versions(self):
        """测试获取配置版本信息"""
        versions = self.loader.get_config_versions()
        assert isinstance(versions, dict)
    
    def test_get_loader_info(self):
        """测试获取加载器信息"""
        info = self.loader.get_loader_info()
        assert isinstance(info, dict)
        assert "config_dir" in info
        assert "auto_reload" in info
        assert "is_loaded" in info


class TestConfigSystemIntegration:
    """配置系统集成测试"""
    
    def setup_method(self):
        """测试前设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.excel_dir = Path(self.temp_dir) / "excel"
        self.json_dir = Path(self.temp_dir) / "json"
        self.generated_dir = Path(self.temp_dir) / "generated"
    
    def teardown_method(self):
        """测试后清理"""
        shutil.rmtree(self.temp_dir)
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流程"""
        # 1. 创建Excel文件
        create_sample_excel_files(str(self.excel_dir))
        
        # 2. 转换Excel到JSON
        converter = ExcelToJsonConverter(
            excel_dir=str(self.excel_dir),
            json_dir=str(self.json_dir)
        )
        convert_results = converter.batch_convert()
        assert any(convert_results.values())
        
        # 3. 生成配置类
        generator = ConfigClassGenerator(
            json_dir=str(self.json_dir),
            output_dir=str(self.generated_dir)
        )
        gen_results = generator.generate_all_configs()
        assert any(gen_results.values())
        
        # 4. 加载配置
        loader = ConfigLoader(config_dir=str(self.json_dir))
        load_success = await loader.load_all_configs()
        assert load_success
        
        # 5. 验证配置可用性
        manager = loader.config_manager
        stats = manager.get_config_count()
        assert stats["total"] > 0
        
        # 测试获取具体配置
        item = manager.get_item(1001)
        assert item is not None
        assert item.name == "小血瓶"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])