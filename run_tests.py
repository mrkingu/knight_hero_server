#!/usr/bin/env python3
"""
测试运行器
Test Runner

作者: lx
日期: 2025-06-18
描述: 统一测试运行脚本，支持单元测试、集成测试、性能测试
"""

import argparse
import sys
import subprocess
import os
from pathlib import Path

def run_unit_tests():
    """运行单元测试"""
    print("Running Unit Tests...")
    cmd = ["python", "-m", "pytest", "test/unit/", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=Path(__file__).parent).returncode

def run_integration_tests():
    """运行集成测试"""
    print("Running Integration Tests...")
    cmd = ["python", "-m", "pytest", "test/integration/", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=Path(__file__).parent).returncode

def run_protocol_tests():
    """运行协议测试"""
    print("Running Protocol Tests...")
    cmd = ["python", "-m", "pytest", "test/unit/test_protocol.py", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=Path(__file__).parent).returncode

def run_gateway_tests():
    """运行网关测试"""
    print("Running Gateway Tests...")
    cmd = ["python", "-m", "pytest", "test/integration/test_gateway.py", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=Path(__file__).parent).returncode

def run_load_tests():
    """运行压力测试"""
    print("Running Load Tests with Locust...")
    print("Note: This requires a running server instance")
    print("To run manually: locust -f test/load/locustfile.py --host=http://localhost:8000")
    return 0

def run_mock_client_test():
    """运行Mock客户端测试"""
    print("Running Mock Client Test...")
    cmd = ["python", "test/utils/mock_client.py"]
    return subprocess.run(cmd, cwd=Path(__file__).parent).returncode

def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("RUNNING ALL TESTS")
    print("="*60)
    
    results = []
    
    # 运行单元测试
    results.append(("Unit Tests", run_unit_tests()))
    
    # 运行集成测试
    results.append(("Integration Tests", run_integration_tests()))
    
    # 打印结果
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, result in results:
        status = "PASSED" if result == 0 else "FAILED"
        print(f"{test_name}: {status}")
        if result != 0:
            all_passed = False
    
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1

def main():
    parser = argparse.ArgumentParser(description="Knight Hero Server Test Runner")
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "protocol", "gateway", "load", "mock", "all"],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # 设置工作目录
    os.chdir(Path(__file__).parent)
    
    # 运行对应的测试
    if args.test_type == "unit":
        return run_unit_tests()
    elif args.test_type == "integration":
        return run_integration_tests()
    elif args.test_type == "protocol":
        return run_protocol_tests()
    elif args.test_type == "gateway":
        return run_gateway_tests()
    elif args.test_type == "load":
        return run_load_tests()
    elif args.test_type == "mock":
        return run_mock_client_test()
    elif args.test_type == "all":
        return run_all_tests()
    else:
        print(f"Unknown test type: {args.test_type}")
        return 1

if __name__ == "__main__":
    sys.exit(main())