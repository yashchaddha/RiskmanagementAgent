#!/usr/bin/env python3
"""
Test script for risk profile functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import RiskProfileDatabaseService
import asyncio

async def test_risk_profile_creation():
    """Test creating default risk profiles for a user"""
    print("🧪 Testing Risk Profile Creation")
    print("=" * 40)
    
    # Test user ID
    test_user_id = "test_user_risk_profile"
    
    # Test creating default profiles
    print(f"Creating default risk profiles for user: {test_user_id}")
    result = await RiskProfileDatabaseService.create_default_risk_profiles(test_user_id)
    
    if result.success:
        print(f"✅ Successfully created {result.data.get('inserted_count', 0)} risk profiles")
    else:
        print(f"❌ Failed to create risk profiles: {result.message}")
        return
    
    # Test retrieving profiles
    print(f"\nRetrieving risk profiles for user: {test_user_id}")
    result = await RiskProfileDatabaseService.get_user_risk_profiles(test_user_id)
    
    if result.success:
        profiles = result.data.get("profiles", [])
        print(f"✅ Successfully retrieved {len(profiles)} risk profiles")
        
        # Display profile information
        for i, profile in enumerate(profiles, 1):
            risk_type = profile.get("riskType", "")
            likelihood_count = len(profile.get("likelihoodScale", []))
            impact_count = len(profile.get("impactScale", []))
            print(f"  {i}. {risk_type} - {likelihood_count}x{impact_count} matrix")
            
            # Show first likelihood and impact levels
            likelihood_scale = profile.get("likelihoodScale", [])
            impact_scale = profile.get("impactScale", [])
            
            if likelihood_scale:
                print(f"     Likelihood: {likelihood_scale[0]['title']} → {likelihood_scale[-1]['title']}")
            if impact_scale:
                print(f"     Impact: {impact_scale[0]['title']} → {impact_scale[-1]['title']}")
    else:
        print(f"❌ Failed to retrieve risk profiles: {result.message}")

async def test_risk_profile_update():
    """Test updating a risk profile"""
    print("\n🧪 Testing Risk Profile Update")
    print("=" * 40)
    
    test_user_id = "test_user_risk_profile"
    
    # Custom likelihood scale for testing
    custom_likelihood = [
        {"level": 1, "title": "Very Rare", "description": "Extremely unlikely to occur"},
        {"level": 2, "title": "Rare", "description": "Unlikely to occur"},
        {"level": 3, "title": "Possible", "description": "May occur occasionally"},
        {"level": 4, "title": "Likely", "description": "Expected to occur"},
        {"level": 5, "title": "Certain", "description": "Will definitely occur"}
    ]
    
    custom_impact = [
        {"level": 1, "title": "Minimal", "description": "Negligible impact"},
        {"level": 2, "title": "Minor", "description": "Small impact"},
        {"level": 3, "title": "Moderate", "description": "Noticeable impact"},
        {"level": 4, "title": "Major", "description": "Significant impact"},
        {"level": 5, "title": "Severe", "description": "Critical impact"}
    ]
    
    print("Updating Strategic Risk profile with custom scales...")
    result = await RiskProfileDatabaseService.update_risk_profile(
        test_user_id, 
        "Strategic Risk", 
        custom_likelihood, 
        custom_impact
    )
    
    if result.success:
        print("✅ Successfully updated Strategic Risk profile")
        
        # Verify the update
        profiles_result = await RiskProfileDatabaseService.get_user_risk_profiles(test_user_id)
        if profiles_result.success:
            profiles = profiles_result.data.get("profiles", [])
            strategic_profile = next((p for p in profiles if p.get("riskType") == "Strategic Risk"), None)
            
            if strategic_profile:
                updated_likelihood = strategic_profile.get("likelihoodScale", [])
                updated_impact = strategic_profile.get("impactScale", [])
                
                print(f"  Updated Likelihood: {updated_likelihood[0]['title']} → {updated_likelihood[-1]['title']}")
                print(f"  Updated Impact: {updated_impact[0]['title']} → {updated_impact[-1]['title']}")
            else:
                print("❌ Could not find updated Strategic Risk profile")
    else:
        print(f"❌ Failed to update risk profile: {result.message}")

async def main():
    """Run all tests"""
    print("🚀 Risk Profile System Tests")
    print("=" * 50)
    
    await test_risk_profile_creation()
    await test_risk_profile_update()
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(main()) 