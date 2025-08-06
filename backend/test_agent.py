import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent

def test_preference_update():
    # Test data
    test_message = "Update my preferences to 4*4 matrix"
    
    # Mock user data
    user_data = {
        "username": "testuser",
        "organization_name": "Test Org",
        "location": "Test Location",
        "domain": "Technology",
        "likelihood": ["Low", "Medium", "High", "Severe", "Critical"],
        "impact": ["Low", "Medium", "High", "Severe", "Critical"]
    }
    
    print("Testing preference update...")
    print(f"Input message: {test_message}")
    print(f"Original user_data: {user_data}")
    
    # Run the agent
    response, conversation_history, risk_context, updated_user_data = run_agent(
        message=test_message,
        conversation_history=[],
        risk_context={},
        user_data=user_data
    )
    
    print(f"\nAgent response: {response}")
    print(f"Updated user_data: {updated_user_data}")
    
    # Check if preferences were updated
    original_likelihood = user_data.get("likelihood", [])
    original_impact = user_data.get("impact", [])
    updated_likelihood = updated_user_data.get("likelihood", [])
    updated_impact = updated_user_data.get("impact", [])
    
    print(f"\nOriginal likelihood: {original_likelihood}")
    print(f"Updated likelihood: {updated_likelihood}")
    print(f"Original impact: {original_impact}")
    print(f"Updated impact: {updated_impact}")
    
    if original_likelihood != updated_likelihood or original_impact != updated_impact:
        print("✅ Preferences were updated!")
    else:
        print("❌ Preferences were not updated")

if __name__ == "__main__":
    test_preference_update() 