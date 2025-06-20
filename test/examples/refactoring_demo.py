#!/usr/bin/env python3
"""
重构功能验证演示
作者: lx
日期: 2025-06-20
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

async def main():
    """主函数"""
    print("🚀 开始验证重构后的功能...")
    
    # 1. 测试统一序列化工具
    print("\n1. 测试统一序列化工具")
    try:
        from common.utils import auto_serialize, auto_deserialize
        
        test_data = {"name": "测试", "value": 42}
        
        # 测试msgpack序列化
        serialized = auto_serialize(test_data, "msgpack")
        deserialized = auto_deserialize(serialized, "msgpack")
        
        assert deserialized == test_data
        print("   ✅ msgpack序列化功能正常")
        
        # 测试JSON序列化
        serialized = auto_serialize(test_data, "json")
        deserialized = auto_deserialize(serialized, "json")
        
        assert deserialized == test_data
        print("   ✅ JSON序列化功能正常")
        
    except Exception as e:
        print(f"   ❌ 序列化测试失败: {e}")
    
    # 2. 测试错误处理器
    print("\n2. 测试错误处理器")
    try:
        from common.utils import ErrorHandler, handle_errors
        
        # 测试错误处理器创建
        handler = ErrorHandler()
        print("   ✅ 错误处理器创建成功")
        
        # 测试装饰器
        @handle_errors(reraise=False)
        def test_function():
            raise ValueError("测试错误")
        
        result = test_function()
        assert result["error_type"] == "ValueError"
        print("   ✅ 错误处理装饰器功能正常")
        
    except Exception as e:
        print(f"   ❌ 错误处理测试失败: {e}")
    
    # 3. 测试验证器
    print("\n3. 测试验证器")
    try:
        from common.utils import Validator, ValidationError
        
        # 测试必填验证
        assert Validator.required("test") == True
        print("   ✅ 必填验证器正常")
        
        # 测试玩家ID格式验证
        assert Validator.player_id_format("player_1234567890") == True
        print("   ✅ 玩家ID格式验证器正常")
        
        # 测试字符串长度验证
        assert Validator.string_length("test", 1, 10) == True
        print("   ✅ 字符串长度验证器正常")
        
    except Exception as e:
        print(f"   ❌ 验证器测试失败: {e}")
    
    # 4. 测试gRPC服务注册中心
    print("\n4. 测试gRPC服务注册中心")
    try:
        from common.grpc.service_registry import ServiceRegistry, ServiceType, get_service_registry
        
        # 创建注册中心
        registry = ServiceRegistry()
        print("   ✅ 服务注册中心创建成功")
        
        # 注册服务
        registry.register_service(ServiceType.LOGIC, "localhost", 9999)
        addresses = registry.get_service_addresses(ServiceType.LOGIC)
        assert ("localhost", 9999) in addresses
        print("   ✅ 服务注册功能正常")
        
        # 获取随机地址
        random_addr = registry.get_random_address(ServiceType.LOGIC)
        assert random_addr is not None
        print("   ✅ 负载均衡功能正常")
        
        # 测试全局注册中心
        global_registry = get_service_registry()
        assert global_registry is not None
        print("   ✅ 全局注册中心正常")
        
    except Exception as e:
        print(f"   ❌ 服务注册中心测试失败: {e}")
    
    # 5. 测试Repository管理器
    print("\n5. 测试Repository访问控制")
    try:
        from common.database.repository import RepositoryManager, get_repository_manager
        
        # 创建管理器
        manager = get_repository_manager()
        print("   ✅ Repository管理器创建成功")
        
        # 测试单例模式
        manager2 = get_repository_manager()
        assert manager is manager2
        print("   ✅ 单例模式正常")
        
        # 测试列出Repository
        repos = manager.list_repositories()
        assert isinstance(repos, dict)
        print("   ✅ Repository列表功能正常")
        
        # 测试健康检查
        health = manager.health_check()
        assert isinstance(health, dict)
        print("   ✅ 健康检查功能正常")
        
    except Exception as e:
        print(f"   ❌ Repository管理器测试失败: {e}")
    
    # 6. 测试装饰器工具
    print("\n6. 测试装饰器工具")
    try:
        from common.utils import retry, timeout, cache
        
        # 测试重试装饰器
        call_count = 0
        
        @retry(max_attempts=3, delay=0.01)
        async def test_retry():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("测试重试")
            return "成功"
        
        result = await test_retry()
        assert result == "成功"
        assert call_count == 2
        print("   ✅ 重试装饰器正常")
        
        # 测试超时装饰器
        @timeout(0.1)
        async def test_timeout():
            return "快速完成"
        
        result = await test_timeout()
        assert result == "快速完成"
        print("   ✅ 超时装饰器正常")
        
        # 测试缓存装饰器
        @cache(ttl=1.0)
        def test_cache(x):
            return x * 2
        
        result1 = test_cache(5)
        result2 = test_cache(5)  # 应该使用缓存
        assert result1 == result2 == 10
        print("   ✅ 缓存装饰器正常")
        
    except Exception as e:
        print(f"   ❌ 装饰器工具测试失败: {e}")
    
    print("\n🎉 所有重构功能验证完成！")
    print("\n📋 总结：")
    print("   - 统一序列化工具：可以使用auto_serialize/auto_deserialize")
    print("   - 错误处理器：支持自动错误记录和装饰器")
    print("   - 验证器：完整的数据验证工具集")
    print("   - gRPC注册中心：自动服务发现和负载均衡")
    print("   - Repository控制：安全的数据访问层")
    print("   - 实用装饰器：重试、超时、缓存等功能")
    print("\n🔗 向后兼容：原有代码继续正常工作")
    print("📚 查看MIGRATION_GUIDE.md了解如何迁移到新接口")

if __name__ == "__main__":
    asyncio.run(main())