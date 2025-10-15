#!/usr/bin/env python3
"""
Dependency resolution script for FinOps Chatbot
"""
import subprocess
import sys
import tempfile
import os


def test_package_compatibility():
    """Test package compatibility by installing in a temporary environment"""
    
    packages = [
        "streamlit>=1.45.0",
        "boto3>=1.38.0", 
        "streamlit-cognito-auth>=1.3.0",
        "strands-agents>=0.1.2",
        "strands-agents-tools>=0.1.1",
        "mcp>=1.8.0",
        "awslabs-aws-api-mcp-server"
    ]
    
    print("🔍 Testing package compatibility...")
    print("=" * 50)
    
    # Test each package individually first
    for package in packages:
        print(f"Testing: {package}")
        try:
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", "--dry-run", package
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"  ✅ {package} - OK")
            else:
                print(f"  ❌ {package} - Error: {result.stderr[:100]}...")
        except Exception as e:
            print(f"  ❌ {package} - Exception: {e}")
    
    print("\n🔍 Testing all packages together...")
    
    # Test all packages together
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "--dry-run"
        ] + packages, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ All packages compatible!")
            return True
        else:
            print("❌ Package conflicts detected:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error testing compatibility: {e}")
        return False


def create_fixed_requirements():
    """Create a fixed requirements.txt with resolved dependencies"""
    
    print("\n🔧 Creating dependency-resolved requirements...")
    
    # Try different approaches
    approaches = [
        {
            "name": "Relaxed Versions",
            "packages": [
                "streamlit",
                "boto3", 
                "streamlit-cognito-auth",
                "strands-agents",
                "strands-agents-tools",
                "mcp",
                "awslabs-aws-api-mcp-server"
            ]
        },
        {
            "name": "Core Only",
            "packages": [
                "streamlit>=1.45.0",
                "boto3>=1.38.0",
                "strands-agents>=0.1.2",
                "mcp>=1.8.0"
            ]
        },
        {
            "name": "Minimal FinOps",
            "packages": [
                "streamlit",
                "boto3",
                "strands-agents",
                "mcp"
            ]
        }
    ]
    
    for approach in approaches:
        print(f"\n📦 Testing approach: {approach['name']}")
        
        # Create temporary requirements file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for package in approach['packages']:
                f.write(f"{package}\n")
            temp_req_file = f.name
        
        try:
            # Test installation
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", "--dry-run", "-r", temp_req_file
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"  ✅ {approach['name']} works!")
                
                # Copy to requirements-fixed.txt
                with open("requirements-fixed.txt", "w") as fixed_file:
                    for package in approach['packages']:
                        fixed_file.write(f"{package}\n")
                
                print(f"  📝 Created requirements-fixed.txt")
                os.unlink(temp_req_file)
                return True
            else:
                print(f"  ❌ {approach['name']} failed: {result.stderr[:200]}...")
                
        except Exception as e:
            print(f"  ❌ {approach['name']} exception: {e}")
        
        finally:
            if os.path.exists(temp_req_file):
                os.unlink(temp_req_file)
    
    return False


def main():
    """Main dependency resolution process"""
    print("🔧 FinOps Chatbot Dependency Resolution")
    print("=" * 50)
    
    # Test current requirements
    if test_package_compatibility():
        print("\n🎉 Current requirements.txt is compatible!")
        return 0
    
    # Try to create fixed requirements
    if create_fixed_requirements():
        print("\n✅ Created requirements-fixed.txt")
        print("💡 Replace requirements.txt with requirements-fixed.txt")
        return 0
    else:
        print("\n❌ Could not resolve dependencies automatically")
        print("\n💡 Manual steps to try:")
        print("1. Update to latest package versions")
        print("2. Remove version pins (use >= instead of ==)")
        print("3. Install packages one by one to identify conflicts")
        print("4. Use pip-tools to generate compatible versions")
        return 1


if __name__ == "__main__":
    sys.exit(main())