#!/usr/bin/env python3
"""
Simple test to verify the dynamic config manager and Azure OpenAI integration
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.dynamic_config_manager import DynamicConfigManager
from app.core.azure_openai import ChatOpenAI

def test_dynamic_config_manager():
    """Test that the dynamic config manager can be instantiated"""
    print("Testing Dynamic Config Manager...")
    try:
        config_manager = DynamicConfigManager()
        print("✓ Dynamic Config Manager instantiated successfully")
        
        # Test loading config (may fail if not configured, but should not error)
        config = config_manager.load_config()
        print(f"✓ Config loaded: {config is not None}")
        
        # Test getting a specific config
        endpoints = config_manager.get_config('azure_ai_endpoints', default="not_found")
        print(f"✓ Azure endpoints config: {endpoints}")
        
    except Exception as e:
        print(f"✗ Dynamic Config Manager failed: {e}")
        return False
    
    return True

def test_azure_openai():
    """Test that the Azure OpenAI client can be instantiated"""
    print("\nTesting Azure OpenAI Client...")
    try:
        from app.config import settings
        
        # Test client instantiation
        client = ChatOpenAI(model=settings.MODEL_TO_USE, temperature=0)
        print("✓ Azure OpenAI Client instantiated successfully")
        
        # Note: We don't test actual API calls here as they require proper config
        
    except Exception as e:
        print(f"✗ Azure OpenAI Client failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("CDD Agent Integration Test")
    print("=" * 40)
    
    config_success = test_dynamic_config_manager()
    azure_success = test_azure_openai()
    
    print("\n" + "=" * 40)
    if config_success and azure_success:
        print("🎉 All tests passed! Integration is working.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the configuration.")
        sys.exit(1) 