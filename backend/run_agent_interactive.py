#!/usr/bin/env python3
"""
Interactive script to run the Risk Management Agent
"""

from agent import run_agent

def main():
    print("🤖 Risk Management Agent - Interactive Mode")
    print("=" * 50)
    print("Type 'quit' to exit")
    print()
    
    conversation_history = []
    risk_context = {}
    user_data = {
        "username": "user",
        "organization_name": "Your Organization",
        "location": "Your Location",
        "domain": "Technology"
    }
    
    while True:
        try:
            # Get user input
            user_input = input("\n💬 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye! Thanks for using the Risk Management Agent.")
                break
            
            if not user_input:
                continue
            
            print("\n🤖 Agent is thinking...")
            
            # Run the agent
            response, conversation_history, risk_context, user_data = run_agent(
                message=user_input,
                conversation_history=conversation_history,
                risk_context=risk_context,
                user_data=user_data
            )
            
            print(f"\n🤖 Agent: {response}")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye! Thanks for using the Risk Management Agent.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Please try again.")

if __name__ == "__main__":
    main()
