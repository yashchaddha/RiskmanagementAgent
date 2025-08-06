def test_comparison():
    # Original user data
    user_data = {
        "username": "testuser",
        "likelihood": ["Low", "Medium", "High", "Severe", "Critical"],
        "impact": ["Low", "Medium", "High", "Severe", "Critical"]
    }
    
    # Updated user data (what the agent returns)
    updated_user_data = {
        "username": "testuser",
        "likelihood": ["Low", "Medium", "High", "Severe"],
        "impact": ["Low", "Medium", "High", "Severe"]
    }
    
    print(f"Original user_data: {user_data}")
    print(f"Updated user_data: {updated_user_data}")
    
    # Test the comparison logic from main.py
    original_likelihood = user_data.get("likelihood", [])
    original_impact = user_data.get("impact", [])
    updated_likelihood = updated_user_data.get("likelihood", [])
    updated_impact = updated_user_data.get("impact", [])
    
    likelihood_changed = original_likelihood != updated_likelihood
    impact_changed = original_impact != updated_impact
    
    print(f"Likelihood changed: {likelihood_changed} ({original_likelihood} -> {updated_likelihood})")
    print(f"Impact changed: {impact_changed} ({original_impact} -> {updated_impact})")
    
    if likelihood_changed or impact_changed:
        print("✅ Changes detected!")
    else:
        print("❌ No changes detected")
    
    # Test direct comparison
    print(f"\nDirect comparison tests:")
    print(f"user_data['likelihood'] != updated_user_data['likelihood']: {user_data['likelihood'] != updated_user_data['likelihood']}")
    print(f"user_data['impact'] != updated_user_data['impact']: {user_data['impact'] != updated_user_data['impact']}")
    
    # Test the original logic from main.py
    if (updated_user_data.get("likelihood") != user_data.get("likelihood") or 
        updated_user_data.get("impact") != user_data.get("impact")):
        print("✅ Original logic detects changes")
    else:
        print("❌ Original logic does not detect changes")

if __name__ == "__main__":
    test_comparison() 