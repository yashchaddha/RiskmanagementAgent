#!/usr/bin/env python3
"""
Test script for the finalized risks summary functionality
"""

import asyncio
import sys
import os

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import get_finalized_risks_summary

def test_finalized_risks_summary():
    """Test the finalized risks summary generation"""
    
    # Sample finalized risks data
    sample_risks = [
        {
            "description": "Data breach due to inadequate cybersecurity measures",
            "category": "Technology",
            "likelihood": "High",
            "impact": "High",
            "treatment_strategy": "Implement comprehensive cybersecurity framework including encryption, access controls, and regular security audits",
            "department": "IT",
            "risk_owner": "CTO",
            "asset_value": "Critical",
            "security_impact": "High",
            "target_date": "2024-06-30",
            "risk_progress": "Identified",
            "residual_exposure": "Medium"
        },
        {
            "description": "Regulatory non-compliance with GDPR requirements",
            "category": "Legal and Compliance",
            "likelihood": "Medium",
            "impact": "High",
            "treatment_strategy": "Conduct GDPR compliance audit, update privacy policies, and implement data protection measures",
            "department": "Legal",
            "risk_owner": "General Counsel",
            "asset_value": "High",
            "security_impact": "Yes",
            "target_date": "2024-05-15",
            "risk_progress": "Ongoing Mitigation",
            "residual_exposure": "Low"
        },
        {
            "description": "Supply chain disruption due to vendor dependency",
            "category": "Operational",
            "likelihood": "Medium",
            "impact": "Medium",
            "treatment_strategy": "Diversify supplier base, establish backup suppliers, and implement supply chain monitoring",
            "department": "Operations",
            "risk_owner": "Operations Manager",
            "asset_value": "Medium",
            "security_impact": "No",
            "target_date": "2024-07-31",
            "risk_progress": "Identified",
            "residual_exposure": "High"
        }
    ]
    
    # Test parameters
    organization_name = "TechCorp Solutions"
    location = "United States"
    domain = "Technology"
    
    print("🧪 Testing Finalized Risks Summary Generation")
    print("=" * 50)
    print(f"Organization: {organization_name}")
    print(f"Location: {location}")
    print(f"Domain: {domain}")
    print(f"Number of risks: {len(sample_risks)}")
    print("\n" + "=" * 50)
    
    try:
        # Generate summary
        summary = get_finalized_risks_summary(sample_risks, organization_name, location, domain)
        
        print("✅ Summary generated successfully!")
        print("\n📊 Generated Summary:")
        print("-" * 50)
        print(summary)
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating summary: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Finalized Risks Summary Test")
    print()
    
    success = test_finalized_risks_summary()
    
    print()
    if success:
        print("✅ Test completed successfully!")
        print("The finalized risks summary functionality is working correctly.")
    else:
        print("❌ Test failed!")
        print("Please check the error message above and fix any issues.")
    
    print("\n📝 Note: This test requires a valid OpenAI API key to be set in your environment.") 