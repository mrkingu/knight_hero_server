"""
Repository生成脚本
扫描所有Model并生成对应的Repository
作者: mrkingu
日期: 2025-06-20
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database.generator.repository_generator import RepositoryGenerator
from pathlib import Path

def main():
    """主函数"""
    # 设置路径
    project_root = Path(__file__).parent.parent
    model_path = project_root / "common" / "database" / "models"
    output_path = project_root / "common" / "database" / "repositories" / "generated"
    
    # 确保输出目录存在
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 创建生成器
    generator = RepositoryGenerator(str(model_path), str(output_path))
    
    # 扫描Models
    print("Scanning models...")
    models = generator.scan_models()
    print(f"Found {len(models)} models")
    
    # 生成Repositories
    print("\nGenerating repositories...")
    for model_name, model_class in models.items():
        print(f"  Generating repository for {model_name}")
        generator.generate_repository(model_name, model_class)
        
    print("\nDone! Generated repositories in:", output_path)
    
    # 生成__init__.py
    init_file = output_path / "__init__.py"
    init_content = []
    
    for py_file in output_path.glob("*_repository.py"):
        module_name = py_file.stem
        class_name = ''.join(word.capitalize() for word in module_name.split('_'))
        init_content.append(f"from .{module_name} import {class_name}")
        
    init_file.write_text('\n'.join(init_content))

if __name__ == "__main__":
    main()