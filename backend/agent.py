import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from dependencies import get_llm
import json

# Try to import the ISO knowledge, fallback to empty dict if import fails
try:
    from knowledge_base import ISO_27001_KNOWLEDGE
except ImportError:
    print("Warning: Could not import ISO_27001_KNOWLEDGE, using empty dict instead")
    ISO_27001_KNOWLEDGE = {}

# Load environment variables from .env
load_dotenv()

# 1. Define the state schema
class LLMState(TypedDict):
    input: str
    output: str
    conversation_history: list
    risk_context: dict  # Store risk assessment context
    user_data: dict  # Store user organization data
    risk_generation_requested: bool  # Flag to indicate if risk generation is needed
    preference_update_requested: bool  # Flag to indicate if preference update is needed
    risk_register_requested: bool  # Flag to indicate if risk register access is needed
    risk_profile_requested: bool  # Flag to indicate if risk profile access is needed
    matrix_recommendation_requested: bool  # Flag to indicate if matrix recommendation is needed
    is_audit_related: bool  # Flag to indicate if query is audit-related
    is_risk_related: bool  # Flag to indicate if query is risk-related

# 2. Define the risk node
def risk_node(state: LLMState):
    print("Risk Node Activated")
    try:
        llm = get_llm()
        
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})
        
        # First, check if this is a risk generation request
        risk_generation_keywords = [
            "generate risks", "recommend risks", "identify risks", "list risks",
            "what risks", "risk assessment", "risk analysis", "risk evaluation",
            "create risks", "develop risks", "produce risks", "risk generation",
            "risk identification", "risk discovery", "risk analysis", "risk review"
        ]
        
        # Check if this is a preference update request
        preference_update_keywords = [
            "update preferences", "change preferences", "modify preferences", "set preferences",
            "update likelihood", "change likelihood", "update impact", "change impact",
            "risk matrix", "matrix size", "3x3", "4x4", "5x5", "3*3", "4*4", "5*5", "current values",
            "show preferences", "view preferences", "get preferences", "preference settings"
        ]
        
        # Check if this is a risk register request
        risk_register_keywords = [
            "open risk register", "show risk register", "view risk register", "display risk register",
            "show finalized risks", "view finalized risks", "display finalized risks", "open finalized risks",
            "risk register", "finalized risks", "show my risks", "view my risks", "display my risks",
            "my risk register", "my finalized risks", "access risk register", "open my risks"
        ]
        
        # Check if this is a risk profile request
        risk_profile_keywords = [
            "show risk profile", "view risk profile", "display risk profile", "open risk profile",
            "risk profile", "my risk profile", "risk categories", "risk scales", "likelihood scale", "impact scale",
            "risk matrix", "risk assessment matrix", "show risk matrix", "view risk matrix",
            "risk preferences", "risk settings", "risk configuration", "risk framework"
        ]
        
        # Check if this is a matrix recommendation request
        matrix_recommendation_keywords = [
            "recommend", "suggest", "create", "generate", "set up", "configure",
            "3x3", "3*3", "4x4", "4*4", "5x5", "5*5", "matrix size", "risk matrix"
        ]
        
        user_input_lower = user_input.lower()
        is_risk_generation_request = any(keyword in user_input_lower for keyword in risk_generation_keywords)
        is_preference_update_request = any(keyword in user_input_lower for keyword in preference_update_keywords)
        is_risk_register_request = any(keyword in user_input_lower for keyword in risk_register_keywords)
        is_risk_profile_request = any(keyword in user_input_lower for keyword in risk_profile_keywords)
        
        # Check for matrix recommendation
        is_matrix_recommendation_request = any(keyword in user_input_lower for keyword in matrix_recommendation_keywords)
        
        # Extract matrix size from user input
        matrix_size = None
        if "3x3" in user_input_lower or "3*3" in user_input_lower:
            matrix_size = "3x3"
        elif "4x4" in user_input_lower or "4*4" in user_input_lower:
            matrix_size = "4x4"
        elif "5x5" in user_input_lower or "5*5" in user_input_lower:
            matrix_size = "5x5"
        

        
        if is_risk_generation_request:
            # Set flag to trigger risk generation
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": True,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False
            }
        
        if is_preference_update_request:
            # Set flag to trigger preference update
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": True,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False
            }
        
        if is_risk_register_request:
            # Set flag to trigger risk register access
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": True,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False
            }
            
        if is_risk_profile_request:
            # Set flag to trigger risk profile access
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": True,
                "matrix_recommendation_requested": False
            }
        
        if is_matrix_recommendation_request and matrix_size:
            # Set flag to trigger matrix recommendation
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": True,
                "matrix_size": matrix_size
            }
        
        # Create a comprehensive system prompt for Risk Management Agent
        system_prompt = """You are an expert Risk Management Agent specializing in organizational risk assessment, compliance management, and risk mitigation strategies. You should:

        1. **Risk Assessment Expertise**: Help organizations identify, analyze, and evaluate various types of risks including:
           - Competition
           - External
           - Financial
           - Innovation
           - Internal
           - Legal and Compliance
           - Operational
           - Project Management
           - Reputational
           - Safety
           - Strategic
           - Technology

        2. **Compliance Knowledge**: Provide guidance on:
           - Industry-specific regulations (SOX, GDPR, HIPAA, PCI-DSS, etc.)
           - Compliance frameworks and standards
           - Risk-based compliance approaches
           - Audit preparation and best practices

        3. **Risk Management Framework**: Assist with:
           - Risk identification and categorization
           - Risk scoring and prioritization
           - Risk mitigation strategies
           - Risk monitoring and reporting
           - Business continuity planning

        4. **Communication Style**:
           - Be professional yet approachable
           - Use clear, actionable language
           - Provide specific examples when relevant
           - Ask clarifying questions to better understand the organization's context
           - Offer practical recommendations

        5. **Context Awareness**: 
           - Remember previous risk assessments and discussions
           - Build on previous recommendations
           - Maintain consistency in risk evaluation approaches

        6. **Risk Generation**: When users ask for risk generation or recommendations:
           - Suggest using the risk generation feature
           - Explain that you can generate organization-specific risks
           - Ask for organization details if not already provided

        Current conversation context: {conversation_history}
        Risk Assessment Context: {risk_context}
        User Organization Data: {user_data}
        """
        
        # Format conversation history for context
        formatted_history = ""
        if conversation_history:
            formatted_history = "\n".join([
                f"User: {msg['user']}\nAssistant: {msg['assistant']}" 
                for msg in conversation_history[-8:]  # Keep last 8 exchanges for context
            ])
        
        # Format risk context
        formatted_risk_context = ""
        if risk_context:
            formatted_risk_context = f"Organization: {risk_context.get('organization', 'Not specified')}\n"
            formatted_risk_context += f"Industry: {risk_context.get('industry', 'Not specified')}\n"
            formatted_risk_context += f"Risk Areas Identified: {', '.join(risk_context.get('risk_areas', []))}\n"
            formatted_risk_context += f"Compliance Requirements: {', '.join(risk_context.get('compliance_requirements', []))}"
        
        # Format user data
        formatted_user_data = ""
        if user_data:
            formatted_user_data = f"Organization: {user_data.get('organization_name', 'Not specified')}\n"
            formatted_user_data += f"Location: {user_data.get('location', 'Not specified')}\n"
            formatted_user_data += f"Domain: {user_data.get('domain', 'Not specified')}"
        
        # Create the full prompt
        full_prompt = f"{system_prompt.format(conversation_history=formatted_history, risk_context=formatted_risk_context, user_data=formatted_user_data)}\n\nUser: {user_input}\nAssistant:"
        
        response = llm.invoke(full_prompt)
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response.content}
        ]
        
        # Update risk context based on the conversation
        updated_risk_context = update_risk_context(risk_context, user_input, response.content)
        
        return {
            "output": response.content,
            "conversation_history": updated_history,
            "risk_context": updated_risk_context,
            "risk_generation_requested": False,
            "preference_update_requested": False
        }
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while processing your risk management query: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False
        }

# 3. Define the risk generation node
def risk_generation_node(state: LLMState):
    """Generate organization-specific risks based on user data"""
    print("Risk Generation Node Activated")
    try:
        llm = get_llm()
        
        user_data = state.get("user_data", {})
        organization_name = user_data.get("organization_name", "the organization")
        location = user_data.get("location", "the current location")
        domain = user_data.get("domain", "the industry domain")
        risks_applicable = user_data.get("risks_applicable", [])
        
        # Get user's risk profiles to use their specific scales
        from database import RiskProfileDatabaseService
        # Synchronously retrieve risk profiles
        result = RiskProfileDatabaseService.get_user_risk_profiles(user_data.get("username", ""))
        
        # Default scales if profiles not available
        default_likelihood = ["Low", "Medium", "High", "Severe", "Critical"]
        default_impact = ["Low", "Medium", "High", "Severe", "Critical"]
        
        if result.success and result.data and result.data.get("profiles"):
            profiles = result.data.get("profiles", [])
            # Use the first profile's scales as default (they should all be 5x5)
            if profiles:
                first_profile = profiles[0]
                default_likelihood = [level["title"] for level in first_profile.get("likelihoodScale", [])]
                default_impact = [level["title"] for level in first_profile.get("impactScale", [])]
        
        # Create a comprehensive prompt for risk generation
        risk_generation_prompt = f"""You are an expert Risk Management Specialist. Generate 10 comprehensive risks specifically applicable to {organization_name} located in {location} operating in the {domain} domain.

IMPORTANT: The user has specified their risk preferences:
- Preferred Risk Likelihood Levels: {default_likelihood}
- Preferred Risk Impact Levels: {default_impact}

When generating risks, use these preference arrays to determine the likelihood and impact levels. The system will automatically select appropriate values from these arrays based on the specific risk context and the organization's characteristics.

Return the risks in the following JSON format ONLY. Do not include any other text or formatting:

{{
  "risks": [
    {{
      "description": "Clear, detailed description of the risk",
      "category": "One of: Competition, External, Financial, Innovation, Internal, Legal and Compliance, Operational, Project Management, Reputational, Safety, Strategic, Technology",
      "likelihood": "High/Medium/Low",
      "impact": "High/Medium/Low",
      "treatment_strategy": "Specific recommendations to mitigate or manage the risk"
    }},
    {{
      "description": "Clear, detailed description of the risk",
      "category": "One of: Competition, External, Financial, Innovation, Internal, Legal and Compliance, Operational, Project Management, Reputational, Safety, Strategic, Technology",
      "likelihood": "High/Medium/Low",
      "impact": "High/Medium/Low",
      "treatment_strategy": "Specific recommendations to mitigate or manage the risk"
    }}
  ]
}}

Generate 10 risks in the JSON array above. Consider the organization's:
- Industry domain and specific challenges
- Geographic location and regulatory environment
- Size and operational complexity
- Current market conditions and trends
- User's risk preferences (Likelihood Levels: {default_likelihood}, Impact Levels: {default_impact})

Make the risks specific and actionable for {organization_name}. Ensure the JSON is valid and properly formatted."""

        response = llm.invoke(risk_generation_prompt)
        
        # Update conversation history
        conversation_history = state.get("conversation_history", [])
        updated_history = conversation_history + [
            {"user": state["input"], "assistant": response.content}
        ]
        
        # Update risk context to include generated risks
        risk_context = state.get("risk_context", {})
        risk_context["generated_risks"] = True
        risk_context["organization"] = organization_name
        risk_context["industry"] = domain
        risk_context["location"] = location
        
        return {
            "output": response.content,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "risk_generation_requested": False  # Reset the flag
        }
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while generating risks for your organization: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False
        }

# 4. Define the preference update node
def risk_register_node(state: LLMState):
    """Handle risk register access requests"""
    print("Risk Register Node Activated")
    try:
        llm = get_llm()

        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})
        
        prompt = f"""You are a Risk Management Agent. The user has requested to access their risk register or view their finalized risks.

User request: "{user_input}"

Provide a helpful response that:
1. Acknowledges their request to access the risk register
2. Explains that you'll open their risk register where they can view all their finalized risks
3. Mentions that they can search, filter, and review their risk assessment data
4. Keep the response concise and friendly

Response:"""
        
        response = llm.invoke(prompt)
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response.content}
        ]
        
        return {
            "output": response.content,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False
        }
        
    except Exception as e:
        error_response = f"I understand you want to access your risk register. I'll open it for you so you can view all your finalized risks."
        
        return {
            "output": error_response,
            "conversation_history": conversation_history + [{"user": user_input, "assistant": error_response}],
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False
        }

def preference_update_node(state: LLMState):
    """Handle user preference updates for risk profiles"""
    print("Preference Update Node Activated")
    try:
        llm = get_llm()

        user_input = state["input"]
        user_data = state.get("user_data", {})
        
        # Get username from user_data (assuming it's passed from main.py)
        username = user_data.get("username", "")
        
        # Get user's current risk profiles
        from database import RiskProfileDatabaseService
        # Synchronously retrieve risk profiles
        result = RiskProfileDatabaseService.get_user_risk_profiles(username)

        if not result.success or not result.data or not result.data.get("profiles"):
            return {
                "output": "I apologize, but I couldn't retrieve your risk profiles. Please try accessing your risk profile dashboard first.",
                "conversation_history": state.get("conversation_history", []),
                "risk_context": state.get("risk_context", {}),
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False
            }
        
        profiles = result.data.get("profiles", [])
        # Use the first profile's scales as current values (they should all be 5x5)
        current_likelihood = ["Low", "Medium", "High", "Severe", "Critical"]
        current_impact = ["Low", "Medium", "High", "Severe", "Critical"]
        
        if profiles:
            first_profile = profiles[0]
            current_likelihood = [level["title"] for level in first_profile.get("likelihoodScale", [])]
            current_impact = [level["title"] for level in first_profile.get("impactScale", [])]
        
        # Check if user wants to see current values
        show_current_keywords = [
            "current", "show", "view", "get", "what are", "display", "see my"
        ]
        
        user_input_lower = user_input.lower()
        wants_to_see_current = any(keyword in user_input_lower for keyword in show_current_keywords)
        
        if wants_to_see_current:
            response_text = f"""📊 **Current Risk Profile Settings**

Your current risk matrix configuration:
- **Likelihood Levels**: {current_likelihood}
- **Impact Levels**: {current_impact}
- **Matrix Size**: {len(current_likelihood)}x{len(current_impact)}
- **Risk Profiles**: {len(profiles)} categories configured

This means your risk assessments will use {len(current_likelihood)} levels for both likelihood and impact evaluation across {len(profiles)} risk categories.

To update your preferences, you can modify individual risk profiles through the risk profile dashboard."""
        else:
            # Since we now use risk profiles, provide guidance on how to update them
            response_text = f"""🔄 **Risk Profile Management**

Your risk preferences are now managed through individual risk profiles. You currently have {len(profiles)} risk categories configured, each with their own assessment scales.

**Current Configuration:**
- **Matrix Size**: {len(current_likelihood)}x{len(current_impact)}
- **Risk Categories**: {len(profiles)} profiles

**To update your preferences:**
1. Access your risk profile dashboard by asking "show my risk profile"
2. Each risk category can be customized independently
3. You can modify likelihood and impact scales for specific risk types
4. Changes are applied per risk category for more granular control

**Available Risk Categories:**
"""
            for profile in profiles:
                risk_type = profile.get("riskType", "")
                response_text += f"• {risk_type}\n"
            
            response_text += "\nThis approach provides more flexibility and category-specific customization."
        
        # Update conversation history
        conversation_history = state.get("conversation_history", [])
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_text}
        ]
        
        return {
            "output": response_text,
            "conversation_history": updated_history,
            "risk_context": state.get("risk_context", {}),
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False
        }
        
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while updating your preferences: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False
        }

# 4. Define the risk profile node
def risk_profile_node(state: LLMState):
    """Handle risk profile requests and display user's risk categories and scales"""
    print("Risk Profile Node Activated")
    try:
        user_input = state["input"]
        user_data = state.get("user_data", {})
        
        # Simple response that directs users to the frontend risk profile table
        response_text = """📊 **Your Risk Profile Dashboard**

I'll open your comprehensive risk assessment framework for you! 

Your risk profile includes:
• **8 Risk Categories** with specialized assessment criteria
• **5x5 Assessment Matrix** for each category
• **Category-Specific Scales** for likelihood and impact
• **Detailed Definitions** and assessment criteria

The risk profile table will show you:
- Strategic Risk
- Operational Risk  
- Financial Risk
- Compliance Risk
- Reputational Risk
- Health and Safety Risk
- Environmental Risk
- Technology Risk

Each category has its own 1-5 scales for both likelihood and impact, ensuring precise and relevant risk assessment for your organization.

**How to use your risk profile:**
• Each risk category has its own specialized assessment criteria
• Use the 1-5 scales to evaluate likelihood and impact for specific risks
• This framework ensures consistent and comprehensive risk assessment
• You can customize these scales based on your organization's needs

To generate risks using these profiles, simply ask me to "generate risks" or "recommend risks" for your organization."""
        
        # Update conversation history
        conversation_history = state.get("conversation_history", [])
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_text}
        ]
        
        return {
            "output": response_text,
            "conversation_history": updated_history,
            "risk_context": state.get("risk_context", {}),
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False
        }
        
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while accessing your risk profile: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False
        }

# 5. Define the matrix recommendation node
def matrix_recommendation_node(state: LLMState):
    """Handle matrix recommendation requests and create appropriate risk profiles"""
    print("Matrix Recommendation Node Activated")
    try:
        user_input = state["input"]
        user_data = state.get("user_data", {})
        matrix_size = state.get("matrix_size", "5x5")
        
        response_text = f"""🎯 **{matrix_size} Risk Matrix Recommendation**

I'll create a comprehensive {matrix_size} risk assessment framework for your organization!

**Matrix Configuration:**
• **Matrix Size**: {matrix_size} (Levels 1-{matrix_size.split('x')[0]})
• **Risk Categories**: 8 specialized categories
• **Assessment Scales**: Customized likelihood and impact scales

**Recommended Risk Categories:**
1. **Strategic Risk** - Long-term business objectives and market positioning
2. **Operational Risk** - Day-to-day business processes and efficiency
3. **Financial Risk** - Financial performance, cash flow, and investments
4. **Compliance Risk** - Regulatory requirements and legal obligations
5. **Reputational Risk** - Brand image and stakeholder perception
6. **Health and Safety Risk** - Employee and public safety
7. **Environmental Risk** - Environmental impact and sustainability
8. **Technology Risk** - IT systems, cybersecurity, and digital transformation

**Next Steps:**
I'll open the risk profile dashboard where you can review and customize the {matrix_size} matrix for each category. You can then edit the likelihood and impact scales to match your organization's specific needs.

The risk profile table will show you all categories with their {matrix_size} assessment scales ready for customization."""
        
        # Update conversation history
        conversation_history = state.get("conversation_history", [])
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_text}
        ]
        
        return {
            "output": response_text,
            "conversation_history": updated_history,
            "risk_context": state.get("risk_context", {}),
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "matrix_size": matrix_size
        }
        
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while creating the matrix recommendation: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False
        }

def update_risk_context(current_context: dict, user_input: str, assistant_response: str) -> dict:
    """Update risk context based on conversation"""
    print("Updating Risk Context")
    context = current_context.copy()
    
    # Extract organization and industry mentions
    org_keywords = ["company", "organization", "firm", "business", "enterprise"]
    industry_keywords = ["banking", "healthcare", "manufacturing", "retail", "technology", "finance", "insurance"]
    
    user_input_lower = user_input.lower()
    
    # Simple keyword-based context extraction
    for keyword in org_keywords:
        if keyword in user_input_lower:
            # Extract organization name (simplified)
            context["organization"] = "Organization mentioned"
            break
    
    for keyword in industry_keywords:
        if keyword in user_input_lower:
            context["industry"] = keyword.title()
            break
    
    return context

def orchestrator_node(state: LLMState) -> LLMState:
    """Node responsible for routing user queries to relevant nodes based on intent classification"""
    print("Orchestrator Activated")
    system_prompt = """
You are an intelligent orchestrator agent responsible for classifying user queries and routing them to the appropriate specialized nodes.

Your task is to analyze the user's query and determine which node should handle it based on the intent.

INTENT CLASSIFICATION RULES:

1. AUDIT-RELATED QUERIES: Route to "audit_facilitator" if the query is about:
   - Organization audits
   - Audit processes
   - Audit findings
   - Audit reports
   - Audit compliance
   - Audit procedures
   - Audit standards
   - Internal audits
   - External audits
   - Audit documentation

2. ISO 27001 QUERIES: Route to "knowledge_node" if the query is about:
   - ISO 27001:2022 standard
   - Information security management
   - ISMS requirements
   - ISO clauses and controls
   - Annex A controls
   - ISO compliance
   - Information security policies
   - Risk management (as it pertains to ISO requirements)
   - Security controls

3. RISK-RELATED QUERIES: Route to "risk_node" if the query is about:
   - Risk assessments and analysis
   - Risk registers and risk entries
   - Risk scoring or risk matrices
   - Risk treatment and mitigation plans
   - Risk generation or identification processes
   - Updating or maintaining risk profiles
   - Risk appetite and tolerance
   - Risk matrix recommendations and prioritization
   - Preference updates related to risk processes
   - Any node-specific risk operations such as risk_generation, preference_update, risk_register, risk_profile, matrix_recommendation

FEW-SHOT EXAMPLES:

User: "What are the audit findings from last quarter?"
Intent: AUDIT-RELATED
Route to: audit_facilitator

User: "Explain Clause 5.2 of ISO 27001"
Intent: ISO 27001
Route to: knowledge_node

User: "I want to start the audit"
Intent: AUDIT-RELATED
Route to: audit_facilitator

User: "What is Annex A.5.23?"
Intent: ISO 27001
Route to: knowledge_node

User: "Show all my audits?"
Intent: AUDIT-RELATED
Route to: audit_facilitator

User: "What are the leadership requirements in ISO 27001?"
Intent: ISO 27001
Route to: knowledge_node

User: "Review our audit documentation"
Intent: AUDIT-RELATED
Route to: audit_facilitator

User: "Explain the risk treatment process in ISO 27001"
Intent: ISO 27001
Route to: knowledge_node

User: "Create a new risk entry in the risk register"
Intent: RISK-RELATED
Route to: risk_node

User: "How do I score and prioritize risks using a risk matrix?"
Intent: RISK-RELATED
Route to: risk_node

User: "Generate risks for the new project scope"
Intent: RISK-RELATED
Route to: risk_node

User: "Update my risk appetite and preferences"
Intent: RISK-RELATED
Route to: risk_node

OUTPUT FORMAT:
You MUST return EXACTLY one of these three strings (nothing else):
- audit_facilitator
- knowledge_node
- risk_node

Do NOT return any other text, explanations, or formatting. Return ONLY the node name.
"""
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    user_data = state.get("user_data", {})
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]
    
    try:
        llm = get_llm()
        response = llm.invoke(messages)
        routing_decision = response.content.strip().lower()
        
        # Validate the routing decision and set appropriate flags
        if "audit_facilitator" in routing_decision:
            return {
                "input": state["input"],
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False,
                "is_audit_related": True,
                "is_risk_related": False
            }
        elif "risk_node" in routing_decision:
            return {
                "input": state["input"],
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False,
                "is_audit_related": False,
                "is_risk_related": True
            }
        else:
            # Default to ISO auditor for any unrecognized response
            print(f"Unrecognized routing decision: '{routing_decision}', defaulting to knowledge_node")
            return {
                "input": state["input"],
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "risk_generation_requested": False,
                "preference_update_requested": False,
                "risk_register_requested": False,
                "risk_profile_requested": False,
                "matrix_recommendation_requested": False,
                "is_audit_related": False,
                "is_risk_related": False,
                "is_knowledge_related": True
            }
    except Exception as e:
        print(f"Error in orchestrator: {e}")
        # Default to ISO auditor if classification fails
        return {
            "input": state["input"],
            "output": "",
            "conversation_history": conversation_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_knowledge_related": True
        }


# 5. Define the knowledge node
def knowledge_node(state: LLMState):
    """Node for handling ISO 27001 and information security knowledge-related queries"""
    print("Knowledge Node Activated")
    try:
        llm = get_llm()
        
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})
# SOURCE OF TRUTH (read-only)
# ${ISO_27001_KNOWLEDGE_CONTENT}

# Replacing with placeholder - actual content will be injected if available
        system_prompt = f"""
ROLE
You are an ISO/IEC 27001:2022 assistant. For any question about ISO 27001:2022 clauses, subclauses, or Annex A controls, you MUST answer strictly from the structured dataset provided below. For general questions about ISO 27001:2022 (not asking for specific clause/control text), you should still answer—succinctly—using general ISO knowledge, and, when helpful, point to the most relevant entries in the dataset.

SOURCE OF TRUTH (read-only)
{ISO_27001_KNOWLEDGE}
# The above JSON is the canonical dataset. Do not invent entries, numbers, or text that are not present here.

SCOPE & ROUTING
1) If the user asks about a specific clause number (e.g., "5", "5.2", "Clause 7.5", "6.1.3"):
   - Look it up under ISO27001_2022 → Clauses.
   - If a top-level clause (4-10) is requested, return its id, title, description, and list all subclauses with ids + titles from the dataset.
   - If a subclause is requested, return its id + title; if the dataset lacks a description for that subclause provide one from your end, it should be relevant to that subclause title

2) If the user asks about Annex A (e.g., "A.5", "A.8.24", "Annex A technological controls"):
   - Look it up under ISO27001_2022 → Annex_A.
   - If an Annex A domain (A.5-A.8) is requested, return its id, title, description, and list all control ids + titles (with descriptions if present).
   - If a specific control (e.g., A.5.23, A.8.11) is requested, return the control id, title, description, and the parent domain (id + title).

3) If the question is generally related to ISO/IEC 27001:2022 but not specifically about clauses/Annex A (e.g., "What is ISO 27001:2022?", "How does certification work?", "What is risk treatment?"):
   - Provide a concise answer based on general ISO knowledge.
   - When relevant, add a short "See also" section pointing to applicable clauses/subclauses or Annex A domains/controls from the dataset.

4) If the question is completely unrelated to ISO/IEC 27001:2022 (e.g., general conversation, other topics):
   - Politely redirect the user to ask ISO 27001:2022 related questions.
   - Example: "I'm specialized in ISO/IEC 27001:2022 compliance guidance. Please ask me questions about information security management systems, ISO 27001 clauses, Annex A controls, or related compliance topics."

5) If the user asks for something not found in the dataset (e.g., an id that doesn't exist in the JSON):
   - Say you couldn't find that exact id in the provided dataset and offer the nearest relevant entries (e.g., the parent clause/domain) if applicable.
   - Do NOT fabricate ids, titles, or descriptions.

MATCHING & NORMALIZATION
- Treat inputs like "clause 5.2", "5.2", "Leadership policy", or "information security policy" as potential matches to dataset items (e.g., 5.2 → "Information security policy"; "information security policy" → likely 5.2 or A.5.1 depending on context).
- Normalize spacing, case, and punctuation. Accept both "Annex A 8.24" and "A.8.24".
- Prefer exact id matches first; if none, resolve by best title/keyword match and explain mapping in one short sentence ("Interpreting '…' as …").


        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ]
        response = llm.invoke(messages)

        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response.content}
        ]
        
        return {
            "output": response.content,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data
        }
    except Exception as e:
        return {
            "output": f"I apologize, but I encountered an error while processing your information security query: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {})
        }

# 6. Build the graph with the state schema
builder = StateGraph(LLMState)
builder.add_node("orchestrator", orchestrator_node)
builder.add_node("risk_node", risk_node)
builder.add_node("risk_generation", risk_generation_node)
builder.add_node("preference_update", preference_update_node)
builder.add_node("risk_register", risk_register_node)
builder.add_node("risk_profile", risk_profile_node)
builder.add_node("matrix_recommendation", matrix_recommendation_node)
builder.add_node("knowledge_node", knowledge_node)
builder.set_entry_point("orchestrator")

# Add conditional routing from orchestrator
def orchestrator_routing(state: LLMState) -> str:
    if state.get("is_audit_related", False):
        return "audit_facilitator"  # Will be implemented later
    elif state.get("is_risk_related", False):
        return "risk_node"
    elif state.get("is_control_related", False):
        return "control_node"
    elif state.get("is_knowledge_related", False):
        return "knowledge_node"
    else:
        return "knowledge_node"  # Default to existing LLM node for risk management queries

# Add conditional edge based on risk generation flag
def should_generate_risks(state: LLMState) -> str:
    if state.get("risk_generation_requested", False):
        return "risk_generation"
    elif state.get("preference_update_requested", False):
        return "preference_update"
    elif state.get("risk_register_requested", False):
        return "risk_register"
    elif state.get("risk_profile_requested", False):
        return "risk_profile"
    elif state.get("matrix_recommendation_requested", False):
        return "matrix_recommendation"
    return "end"

# Add orchestrator routing
builder.add_conditional_edges("orchestrator", orchestrator_routing, {
    "audit_facilitator": "risk_node",  # Temporary routing to risk_node until audit_facilitator is implemented
    "knowledge_node": "knowledge_node",  # Route to knowledge node for ISO 27001 related queries
    "risk_node": "risk_node"
})

builder.add_conditional_edges("risk_node", should_generate_risks, {
    "risk_generation": "risk_generation",
    "preference_update": "preference_update",
    "risk_register": "risk_register",
    "risk_profile": "risk_profile",
    "matrix_recommendation": "matrix_recommendation",
    "end": END
})
builder.add_edge("risk_generation", END)
builder.add_edge("preference_update", END)
builder.add_edge("risk_register", END)
builder.add_edge("risk_profile", END)
builder.add_edge("matrix_recommendation", END)
builder.add_edge("knowledge_node", END)

graph = builder.compile()

def run_agent(message: str, conversation_history: list = None, risk_context: dict = None, user_data: dict = None):
    if conversation_history is None:
        conversation_history = []
    if risk_context is None:
        risk_context = {}
    if user_data is None:
        user_data = {}
    
    state = {
        "input": message, 
        "output": "", 
        "conversation_history": conversation_history,
        "risk_context": risk_context,
        "user_data": user_data,
        "risk_generation_requested": False,
        "preference_update_requested": False,
        "risk_register_requested": False,
        "risk_profile_requested": False,
        "matrix_recommendation_requested": False,
        "is_audit_related": False,
        "is_risk_related": False
    }
    result = graph.invoke(state)
    return result["output"], result["conversation_history"], result["risk_context"], result["user_data"]

def get_risk_assessment_summary(conversation_history: list, risk_context: dict) -> str:
    """Generate a summary of the risk assessment session"""
    try:
        llm = get_llm()

        # Format conversation for summary
        conversation_text = "\n".join([
            f"User: {msg['user']}\nAssistant: {msg['assistant']}" 
            for msg in conversation_history
        ])
        
        prompt = f"""Based on the following risk management conversation, provide a concise summary of:
        1. Key risks identified
        2. Compliance requirements discussed
        3. Recommendations provided
        4. Next steps suggested

        Conversation:
        {conversation_text}

        Risk Context: {risk_context}

        Please provide a structured summary that could be used for reporting purposes."""
        
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        return "Unable to generate risk assessment summary due to an error."

def get_finalized_risks_summary(finalized_risks: list, organization_name: str, location: str, domain: str) -> str:
    """Generate a comprehensive summary based on finalized risks"""
    try:
        llm = get_llm()

        # Format finalized risks for summary
        risks_text = ""
        for i, risk in enumerate(finalized_risks, 1):
            risks_text += f"""
Risk {i}:
- Description: {risk.description}
- Category: {risk.category}
- Likelihood: {risk.likelihood}
- Impact: {risk.impact}
- Treatment Strategy: {risk.treatment_strategy}
- Department: {risk.department or 'Not specified'}
- Risk Owner: {risk.risk_owner or 'Not assigned'}
- Asset Value: {risk.asset_value or 'Not specified'}
- Security Impact: {risk.security_impact or 'Not specified'}
- Target Date: {risk.target_date or 'Not specified'}
- Risk Progress: {risk.risk_progress or 'Identified'}
- Residual Exposure: {risk.residual_exposure or 'Not assessed'}
"""
        
        prompt = f"""Based on the finalized risks for {organization_name} located in {location} operating in the {domain} domain, provide a comprehensive risk assessment summary.

Finalized Risks:
{risks_text}

Please provide a structured summary that includes:

1. **Executive Summary**
   - Total number of risks finalized
   - Overall risk profile and key concerns
   - Critical risks requiring immediate attention

2. **Risk Distribution Analysis**
   - Breakdown by risk categories
   - Distribution by likelihood and impact levels
   - High-priority risks (High likelihood + High impact)

3. **Department and Ownership Analysis**
   - Risks by department
   - Risk ownership distribution
   - Areas requiring additional oversight

4. **Treatment Strategy Overview**
   - Common mitigation approaches
   - Resource requirements
   - Timeline considerations

5. **Compliance and Security Considerations**
   - Regulatory implications
   - Security impact assessment
   - Compliance gaps identified

6. **Next Steps and Recommendations**
   - Immediate actions required
   - Resource allocation priorities
   - Monitoring and review schedule

Please format this as a professional risk assessment report suitable for executive review."""
        
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        return f"Unable to generate finalized risks summary due to an error: {str(e)}"

# Static greeting message
GREETING_MESSAGE = """Welcome to the Risk Management Agent! I'm here to help your organization with comprehensive risk assessment, compliance management, and risk mitigation strategies. 

I can assist you with identifying operational, financial, strategic, and compliance risks, as well as provide guidance on industry regulations and best practices. 

What specific risk management challenges or compliance requirements would you like to discuss today?"""