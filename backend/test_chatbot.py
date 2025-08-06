#!/usr/bin/env python3
"""
Test script for the chatbot functionality.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_greeting():
    """Test the greeting functionality."""
    print("🧪 Testing Greeting Functionality")
    print("=" * 40)
    
    try:
        from agent import get_greeting
        
        # Test greeting without user name
        print("Testing greeting without user name...")
        greeting = get_greeting()
        print(f"✅ Greeting: {greeting}")
        
        # Test greeting with user name
        print("\nTesting greeting with user name...")
        greeting_with_name = get_greeting("John")
        print(f"✅ Personalized greeting: {greeting_with_name}")
        
    except Exception as e:
        print(f"❌ Error testing greeting: {e}")
        return False
    
    return True

def test_chat():
    """Test the chat functionality."""
    print("\n🧪 Testing Chat Functionality")
    print("=" * 40)
    
    try:
        from agent import run_agent
        
        # Test simple message
        print("Testing simple message...")
        response, history = run_agent("Hello, how are you?")
        print(f"✅ Response: {response}")
        print(f"✅ History length: {len(history)}")
        
        # Test follow-up message
        print("\nTesting follow-up message...")
        response2, history2 = run_agent("What's the weather like?", history)
        print(f"✅ Follow-up response: {response2}")
        print(f"✅ Updated history length: {len(history2)}")
        
    except Exception as e:
        print(f"❌ Error testing chat: {e}")
        return False
    
    return True

def check_environment():
    """Check if environment is properly configured."""
    print("🔧 Checking Environment Configuration")
    print("=" * 40)
    
    # Check OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    elif api_key == "your_openai_api_key_here":
        print("❌ OPENAI_API_KEY is still set to placeholder value")
        return False
    else:
        print("✅ OPENAI_API_KEY is configured")
    
    # Check JWT secret
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        print("❌ JWT_SECRET not found in environment")
        return False
    else:
        print("✅ JWT_SECRET is configured")
    
    return True

def main():
    """Run all tests."""
    print("🤖 AI Chatbot Test Suite")
    print("=" * 50)
    
    # Check environment first
    if not check_environment():
        print("\n❌ Environment not properly configured!")
        print("Please run: python3 setup_env.py")
        return
    
    print("\n" + "=" * 50)
    
    # Test greeting
    greeting_success = test_greeting()
    
    # Test chat
    chat_success = test_chat()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    if greeting_success and chat_success:
        print("✅ All tests passed! Your chatbot is ready to use.")
        print("\n🚀 Next steps:")
        print("1. Start the backend: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        print("2. Start the frontend: cd ../frontend && npm run dev")
        print("3. Open http://localhost:5173 in your browser")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        if not greeting_success:
            print("- Greeting functionality has issues")
        if not chat_success:
            print("- Chat functionality has issues")

if __name__ == "__main__":
    main() 