"""
配置加载器模块
Configuration Loader Module

作者: lx
日期: 2025-06-18
描述: 启动时加载所有配置，配置缓存在内存，支持热更新和版本管理
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import logging
import hashlib
from dataclasses import dataclass

from .base_config import (
    BaseConfig, ItemConfig, SkillConfig, NpcConfig, 
    ConfigManager, get_config_manager
)

# 设置日志
logger = logging.getLogger(__name__)


@dataclass
class ConfigVersion:
    """配置版本信息"""
    version: str
    timestamp: datetime
    file_hash: str
    file_path: str


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_dir: str = "json", auto_reload: bool = False):
        """初始化配置加载器
        
        Args:
            config_dir: 配置文件目录
            auto_reload: 是否启用自动重载
        """
        self.config_dir = Path(config_dir)
        self.auto_reload = auto_reload
        
        # 配置管理器
        self.config_manager = get_config_manager()
        
        # 配置版本管理
        self.config_versions: Dict[str, ConfigVersion] = {}
        
        # 文件监控
        self._file_watchers: Dict[str, float] = {}  # 文件路径 -> 修改时间
        self._reload_callbacks: List[Callable[[str], None]] = []
        
        # 加载状态
        self._is_loaded = False
        self._loading_lock = asyncio.Lock()
        
    async def load_all_configs(self) -> bool:
        """加载所有配置文件
        
        Returns:
            加载是否成功
        """
        async with self._loading_lock:
            try:
                logger.info("开始加载配置文件...")
                
                # 清空现有配置
                self.config_manager.clear_all()
                self.config_versions.clear()
                
                # 扫描配置文件
                config_files = self._scan_config_files()
                
                if not config_files:
                    logger.warning("未找到配置文件")
                    return False
                    
                # 加载各种配置
                success_count = 0
                total_count = len(config_files)
                
                for config_file in config_files:
                    try:
                        success = await self._load_config_file(config_file)
                        if success:
                            success_count += 1
                        else:
                            logger.error(f"加载配置文件失败: {config_file}")
                    except Exception as e:
                        logger.error(f"加载配置文件 {config_file} 时发生异常: {e}")
                        
                # 验证配置完整性
                validation_errors = self.config_manager.validate_all_configs()
                if any(validation_errors.values()):
                    logger.warning(f"配置验证发现问题: {validation_errors}")
                    
                # 设置加载状态
                self._is_loaded = success_count > 0
                
                # 启动文件监控
                if self.auto_reload and self._is_loaded:
                    await self._start_file_watching()
                    
                logger.info(f"配置加载完成: {success_count}/{total_count} 个文件加载成功")
                
                # 输出配置统计
                stats = self.config_manager.get_config_count()
                logger.info(f"配置统计: {stats}")
                
                return self._is_loaded
                
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                return False
                
    def _scan_config_files(self) -> List[Path]:
        """扫描配置文件
        
        Returns:
            配置文件路径列表
        """
        if not self.config_dir.exists():
            logger.warning(f"配置目录不存在: {self.config_dir}")
            return []
            
        config_files = []
        for json_file in self.config_dir.glob('*.json'):
            # 排除服务器配置文件
            if json_file.stem != 'server_config':
                config_files.append(json_file)
                
        return sorted(config_files)
        
    async def _load_config_file(self, config_file: Path) -> bool:
        """加载单个配置文件
        
        Args:
            config_file: 配置文件路径
            
        Returns:
            加载是否成功
        """
        try:
            # 读取文件
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not isinstance(data, dict):
                logger.error(f"配置文件格式错误: {config_file}")
                return False
                
            # 根据文件名确定配置类型
            config_type = config_file.stem.lower()
            
            # 加载对应类型的配置
            if config_type == 'item':
                return await self._load_item_configs(data, config_file)
            elif config_type == 'skill':
                return await self._load_skill_configs(data, config_file)
            elif config_type == 'npc':
                return await self._load_npc_configs(data, config_file)
            else:
                logger.warning(f"未知的配置类型: {config_type}")
                return False
                
        except Exception as e:
            logger.error(f"加载配置文件 {config_file} 失败: {e}")
            return False
            
    async def _load_item_configs(self, data: Dict[str, Any], config_file: Path) -> bool:
        """加载道具配置
        
        Args:
            data: 配置数据
            config_file: 配置文件路径
            
        Returns:
            加载是否成功
        """
        try:
            success_count = 0
            for item_id_str, item_data in data.items():
                try:
                    # 创建配置对象
                    item_config = ItemConfig(**item_data)
                    
                    # 存储到管理器
                    item_id = int(item_id_str)
                    self.config_manager.item_config[item_id] = item_config
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"加载道具配置 {item_id_str} 失败: {e}")
                    
            # 记录版本信息
            await self._record_config_version(config_file, 'item')
            
            logger.info(f"加载道具配置: {success_count} 个")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"加载道具配置失败: {e}")
            return False
            
    async def _load_skill_configs(self, data: Dict[str, Any], config_file: Path) -> bool:
        """加载技能配置
        
        Args:
            data: 配置数据
            config_file: 配置文件路径
            
        Returns:
            加载是否成功
        """
        try:
            success_count = 0
            for skill_id_str, skill_data in data.items():
                try:
                    # 创建配置对象
                    skill_config = SkillConfig(**skill_data)
                    
                    # 存储到管理器
                    skill_id = int(skill_id_str)
                    self.config_manager.skill_config[skill_id] = skill_config
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"加载技能配置 {skill_id_str} 失败: {e}")
                    
            # 记录版本信息
            await self._record_config_version(config_file, 'skill')
            
            logger.info(f"加载技能配置: {success_count} 个")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"加载技能配置失败: {e}")
            return False
            
    async def _load_npc_configs(self, data: Dict[str, Any], config_file: Path) -> bool:
        """加载NPC配置
        
        Args:
            data: 配置数据
            config_file: 配置文件路径
            
        Returns:
            加载是否成功
        """
        try:
            success_count = 0
            for npc_id_str, npc_data in data.items():
                try:
                    # 创建配置对象
                    npc_config = NpcConfig(**npc_data)
                    
                    # 存储到管理器
                    npc_id = int(npc_id_str)
                    self.config_manager.npc_config[npc_id] = npc_config
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"加载NPC配置 {npc_id_str} 失败: {e}")
                    
            # 记录版本信息
            await self._record_config_version(config_file, 'npc')
            
            logger.info(f"加载NPC配置: {success_count} 个")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"加载NPC配置失败: {e}")
            return False
            
    async def _record_config_version(self, config_file: Path, config_type: str):
        """记录配置版本信息
        
        Args:
            config_file: 配置文件路径
            config_type: 配置类型
        """
        try:
            # 计算文件哈希
            with open(config_file, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                
            # 生成版本号
            version = f"{config_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 创建版本信息
            config_version = ConfigVersion(
                version=version,
                timestamp=datetime.now(),
                file_hash=file_hash,
                file_path=str(config_file)
            )
            
            self.config_versions[config_type] = config_version
            
        except Exception as e:
            logger.error(f"记录配置版本失败: {e}")
            
    async def _start_file_watching(self):
        """启动文件监控"""
        try:
            # 记录初始文件修改时间
            config_files = self._scan_config_files()
            for config_file in config_files:
                if config_file.exists():
                    self._file_watchers[str(config_file)] = config_file.stat().st_mtime
                    
            logger.info("启动配置文件监控")
            
            # 启动监控任务
            asyncio.create_task(self._file_watch_loop())
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            
    async def _file_watch_loop(self):
        """文件监控循环"""
        while self.auto_reload:
            try:
                await asyncio.sleep(5)  # 每5秒检查一次
                
                changed_files = []
                for file_path, last_mtime in self._file_watchers.items():
                    file_obj = Path(file_path)
                    if file_obj.exists():
                        current_mtime = file_obj.stat().st_mtime
                        if current_mtime > last_mtime:
                            changed_files.append(file_obj)
                            self._file_watchers[file_path] = current_mtime
                            
                # 重载变更的文件
                for changed_file in changed_files:
                    logger.info(f"检测到配置文件变更: {changed_file}")
                    await self._reload_config_file(changed_file)
                    
            except Exception as e:
                logger.error(f"文件监控循环异常: {e}")
                await asyncio.sleep(10)  # 异常时等待更长时间
                
    async def _reload_config_file(self, config_file: Path):
        """重载单个配置文件
        
        Args:
            config_file: 配置文件路径
        """
        try:
            logger.info(f"重载配置文件: {config_file}")
            
            # 清空对应类型的配置
            config_type = config_file.stem.lower()
            if config_type == 'item':
                self.config_manager.item_config.clear()
            elif config_type == 'skill':
                self.config_manager.skill_config.clear()
            elif config_type == 'npc':
                self.config_manager.npc_config.clear()
                
            # 重新加载
            success = await self._load_config_file(config_file)
            
            if success:
                logger.info(f"配置文件重载成功: {config_file}")
                
                # 调用重载回调
                for callback in self._reload_callbacks:
                    try:
                        callback(str(config_file))
                    except Exception as e:
                        logger.error(f"重载回调执行失败: {e}")
            else:
                logger.error(f"配置文件重载失败: {config_file}")
                
        except Exception as e:
            logger.error(f"重载配置文件 {config_file} 失败: {e}")
            
    def add_reload_callback(self, callback: Callable[[str], None]):
        """添加重载回调函数
        
        Args:
            callback: 回调函数，参数为配置文件路径
        """
        self._reload_callbacks.append(callback)
        
    def remove_reload_callback(self, callback: Callable[[str], None]):
        """移除重载回调函数
        
        Args:
            callback: 要移除的回调函数
        """
        if callback in self._reload_callbacks:
            self._reload_callbacks.remove(callback)
            
    async def reload_all_configs(self) -> bool:
        """重载所有配置
        
        Returns:
            重载是否成功
        """
        logger.info("手动重载所有配置")
        return await self.load_all_configs()
        
    def is_loaded(self) -> bool:
        """检查配置是否已加载
        
        Returns:
            是否已加载
        """
        return self._is_loaded
        
    def get_config_versions(self) -> Dict[str, ConfigVersion]:
        """获取配置版本信息
        
        Returns:
            配置版本信息字典
        """
        return self.config_versions.copy()
        
    def get_loader_info(self) -> Dict[str, Any]:
        """获取加载器信息
        
        Returns:
            加载器信息字典
        """
        config_files = self._scan_config_files()
        
        return {
            "config_dir": str(self.config_dir),
            "auto_reload": self.auto_reload,
            "is_loaded": self._is_loaded,
            "config_files_count": len(config_files),
            "config_files": [f.name for f in config_files],
            "watched_files_count": len(self._file_watchers),
            "reload_callbacks_count": len(self._reload_callbacks),
            "config_versions": {k: v.version for k, v in self.config_versions.items()},
            "last_check_time": datetime.now().isoformat()
        }


# 全局配置加载器实例
config_loader = ConfigLoader()


def get_config_loader() -> ConfigLoader:
    """获取全局配置加载器实例
    
    Returns:
        全局配置加载器实例
    """
    return config_loader


async def initialize_configs(config_dir: str = "json", auto_reload: bool = False) -> bool:
    """初始化配置系统
    
    Args:
        config_dir: 配置目录
        auto_reload: 是否启用自动重载
        
    Returns:
        初始化是否成功
    """
    global config_loader
    config_loader = ConfigLoader(config_dir, auto_reload)
    return await config_loader.load_all_configs()


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        """主函数"""
        # 初始化配置
        success = await initialize_configs(auto_reload=True)
        
        if success:
            print("配置初始化成功")
            
            # 获取加载器信息
            info = config_loader.get_loader_info()
            print(f"加载器信息: {info}")
            
            # 获取配置管理器
            manager = get_config_manager()
            stats = manager.get_config_count()
            print(f"配置统计: {stats}")
            
            # 模拟运行一段时间（用于测试热更新）
            print("运行中...（可以修改配置文件测试热更新）")
            await asyncio.sleep(30)
            
        else:
            print("配置初始化失败")
    
    # 运行主函数
    asyncio.run(main())