#!/usr/bin/env python3
"""
Test runner script for FinOps Chatbot
"""
import subprocess
import sys
import os


def run_tests():
    """Run the test suite with different configurations"""
    
    print("🧪 FinOps Chatbot Test Suite")
    print("=" * 50)
    
    # Check if test dependencies are installed
    try:
        import pytest
        print("✅ pytest is available")
    except ImportError:
        print("❌ pytest not found. Installing test dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "tests/requirements-test.txt"])
    
    # Test configurations
    test_configs = [
        {
            "name": "Unit Tests (Fast)",
            "command": ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "-m", "not slow and not integration"]
        },
        {
            "name": "All Tests",
            "command": ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
        },
        {
            "name": "Coverage Report",
            "command": ["python", "-m", "pytest", "tests/", "--cov=.", "--cov-report=html", "--cov-report=term-missing"]
        },
        {
            "name": "Integration Tests (Requires AWS)",
            "command": ["python", "-m", "pytest", "tests/", "-v", "-m", "integration or aws"]
        }
    ]
    
    # Run tests based on command line argument
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        
        if test_type == "fast":
            config = test_configs[0]
        elif test_type == "all":
            config = test_configs[1]
        elif test_type == "coverage":
            config = test_configs[2]
        elif test_type == "integration":
            config = test_configs[3]
        else:
            print(f"❌ Unknown test type: {test_type}")
            print("Available options: fast, all, coverage, integration")
            return 1
        
        print(f"\n🚀 Running: {config['name']}")
        print("-" * 30)
        result = subprocess.run(config["command"])
        return result.returncode
    
    else:
        # Interactive mode
        print("\nAvailable test configurations:")
        for i, config in enumerate(test_configs, 1):
            print(f"{i}. {config['name']}")
        
        try:
            choice = input("\nSelect test configuration (1-4) or 'q' to quit: ").strip()
            
            if choice.lower() == 'q':
                return 0
            
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(test_configs):
                config = test_configs[choice_idx]
                print(f"\n🚀 Running: {config['name']}")
                print("-" * 30)
                result = subprocess.run(config["command"])
                return result.returncode
            else:
                print("❌ Invalid choice")
                return 1
                
        except (ValueError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            return 0


def main():
    """Main entry point"""
    # Change to the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    return run_tests()


if __name__ == "__main__":
    sys.exit(main())