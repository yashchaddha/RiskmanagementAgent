import asyncio
import requests
import json

async def test_preference_update():
    # Test data
    test_message = "Update my preferences to 4*4 matrix"
    
    # Simulate a chat request
    chat_data = {
        "message": test_message,
        "conversation_history": [],
        "risk_context": {}
    }
    
    # Make request to the chat endpoint
    try:
        response = requests.post(
            "http://localhost:8000/chat",
            json=chat_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Chat request successful")
            print(f"Response: {result['response']}")
            print(f"Conversation history length: {len(result['conversation_history'])}")
        else:
            print(f"❌ Chat request failed with status {response.status_code}")
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Error making request: {e}")

if __name__ == "__main__":
    asyncio.run(test_preference_update()) 