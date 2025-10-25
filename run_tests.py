#!/usr/bin/env python3
"""
Test runner using pytest for the updated functionality
"""
import sys
import os
import subprocess

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.server.example.settings')


def run_pytest_tests():
    """Run tests using pytest"""
    print("🧪 Running tests with pytest...")
    print("=" * 50)
    
    # Run all tests
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/", 
        "-v", 
        "--tb=short",
        "--disable-warnings"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        return result.returncode == 0
    
    except Exception as e:
        print(f"❌ Error running pytest: {e}")
        return False


def run_specific_tests():
    """Run specific test categories"""
    test_commands = [
        {
            "name": "Handler Tests",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_handler.py", "-v"]
        },
        {
            "name": "Integration Tests", 
            "cmd": [sys.executable, "-m", "pytest", "tests/test_consumer_integration_fixed.py", "-v"]
        },
        {
            "name": "Connection Tests",
            "cmd": [sys.executable, "-m", "pytest", "tests/test_connect.py", "-v"]
        }
    ]
    
    results = []
    
    for test in test_commands:
        print(f"\n🔍 Running {test['name']}...")
        print("-" * 40)
        
        try:
            result = subprocess.run(test['cmd'], capture_output=True, text=True)
            success = result.returncode == 0
            results.append((test['name'], success))
            
            if success:
                print(f"✅ {test['name']} - PASSED")
            else:
                print(f"❌ {test['name']} - FAILED")
                print("Error output:")
                print(result.stderr)
        
        except Exception as e:
            print(f"❌ Error running {test['name']}: {e}")
            results.append((test['name'], False))
    
    return results


def main():
    """Main test runner"""
    print("Django NATS Consumer - Pytest Test Suite")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--specific":
        # Run specific test categories
        results = run_specific_tests()
        
        print(f"\n📊 Test Summary:")
        print("=" * 30)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{name:<20} {status}")
        
        print(f"\nTotal: {passed}/{total} test suites passed")
        
        return 0 if passed == total else 1
    
    else:
        # Run all tests
        success = run_pytest_tests()
        
        if success:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print("\n❌ Some tests failed!")
            return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
