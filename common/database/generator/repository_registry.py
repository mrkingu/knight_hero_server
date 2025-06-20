"""
Repository自动注册
扫描并注册所有生成的Repository
作者: mrkingu
日期: 2025-06-20
"""
import importlib
import inspect
from pathlib import Path
from ..repository.base_repository import BaseRepository

class RepositoryRegistry:
    """Repository注册器"""
    
    @staticmethod
    def auto_register(repository_path: str):
        """自动注册所有Repository"""
        repo_path = Path(repository_path)
        registered = []
        
        for py_file in repo_path.glob("*_repository.py"):
            if py_file.name == "base_repository.py":
                continue
                
            module_name = py_file.stem
            try:
                # 构建模块路径
                module_path = f"common.database.repositories.generated.{module_name}"
                module = importlib.import_module(module_path)
                
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        name.endswith("Repository") and
                        issubclass(obj, BaseRepository) and
                        obj != BaseRepository):
                        registered.append((name, obj))
                        
            except ImportError as e:
                print(f"Warning: Could not import {module_name}: {e}")
                
        return registered