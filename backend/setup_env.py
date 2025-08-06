#!/usr/bin/env python3
"""
Setup script to create .env file for the chatbot application.
"""

import os
import getpass

def create_env_file():
    """Create a .env file with required environment variables."""
    
    print("🤖 AI Chatbot Environment Setup")
    print("=" * 40)
    
    # Check if .env already exists
    if os.path.exists('.env'):
        overwrite = input("⚠️  .env file already exists. Overwrite? (y/N): ").lower()
        if overwrite != 'y':
            print("❌ Setup cancelled.")
            return
    
    # Get OpenAI API key
    print("\n🔑 OpenAI API Key")
    print("Get your API key from: https://platform.openai.com/api-keys")
    openai_key = getpass.getpass("Enter your OpenAI API key: ").strip()
    
    if not openai_key:
        print("❌ OpenAI API key is required!")
        return
    
    # Get JWT secret
    print("\n🔐 JWT Secret")
    print("This should be a strong secret for production use.")
    jwt_secret = getpass.getpass("Enter JWT secret (or press Enter for default): ").strip()
    
    if not jwt_secret:
        jwt_secret = "your-super-secret-jwt-key-change-this-in-production"
        print("⚠️  Using default JWT secret. Change this in production!")
      
    # Get MongoDB URI (optional)
    print("\n🗄️  MongoDB URI (optional)")
    print("Leave empty if you don't have MongoDB set up.")
    mongodb_uri = input("Enter MongoDB URI (default: mongodb://localhost:27017): ").strip()
    
    if not mongodb_uri:
        mongodb_uri = "mongodb://localhost:27017"
    
    # Create .env file
    env_content = f"""# OpenAI API Configuration
OPENAI_API_KEY={openai_key}

# Database Configuration
MONGODB_URI={mongodb_uri}

# JWT Secret (change this in production!)
JWT_SECRET={jwt_secret}
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        
        print("\n✅ .env file created successfully!")
        print("\n📝 Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Start the server: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        print("3. Open frontend in another terminal: cd ../frontend && npm run dev")
        print("\n💡 New Features:")
        print("- Signup now includes Organization Name, Location, and Domain fields")
        print("- Chatbot provides personalized greetings using organization information")
        
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

if __name__ == "__main__":
    create_env_file() 