import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dependencies import get_llm
from agent import make_llm_call_with_history
from rag_tools import semantic_risk_search, get_risk_profiles, knowledge_base_search
from models import LLMState
import json
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from database import RiskProfileDatabaseService
import traceback

# Load environment variables from .env
load_dotenv()

# Set up LangSmith project name
LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")

def risk_node(state: LLMState):
    """
    Risk sub-router with stickiness for follow-up queries
    
    Routing Logic:
    1. Risk Operations (generate, create) → risk_generation_node
    2. Risk Information/Questions → risk_knowledge_node  
    3. Risk Register (search, find) → risk_register_node
    4. Matrix Recommendations → matrix_recommendation_node
    """
    print("Risk Node (Intent Router) Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})
        active_mode = state.get("active_mode", "")
        
        # Stickiness BEFORE LLM - check for short follow-ups
        user_text_lower = user_input.lower()
        user_text_len = len(user_input)
        follow_up_keywords = ["filter", "sort", "only", "add", "exclude"]
        is_short_followup = user_text_len <= 80 and any(kw in user_text_lower for kw in follow_up_keywords)
        
        sticky_modes = ["risk_register_node", "risk_generation_node", "matrix_recommendation_node", "risk_knowledge_node"]
        
        if active_mode in sticky_modes and is_short_followup:
            print(f"Stickiness activated: staying in {active_mode}")
            # Re-emit flags for the same destination and return early
            if active_mode == "risk_register_node":
                return {
                    "output": "",
                    "conversation_history": conversation_history,
                    "risk_context": risk_context,
                    "user_data": user_data,
                    "active_mode": "risk_register_node",
                    "risk_generation_requested": False,
                    "risk_register_requested": True,
                    "matrix_recommendation_requested": False,
                    "is_risk_knowledge_related": False
                }
            elif active_mode == "risk_generation_node":
                return {
                    "output": "",
                    "conversation_history": conversation_history,
                    "risk_context": risk_context,
                    "user_data": user_data,
                    "active_mode": "risk_generation_node",
                    "risk_generation_requested": True,
                    "risk_register_requested": False,
                    "matrix_recommendation_requested": False,
                    "is_risk_knowledge_related": False
                }
            elif active_mode == "matrix_recommendation_node":
                return {
                    "output": "",
                    "conversation_history": conversation_history,
                    "risk_context": risk_context,
                    "user_data": user_data,
                    "active_mode": "matrix_recommendation_node",
                    "risk_generation_requested": False,
                    "risk_register_requested": False,
                    "matrix_recommendation_requested": True,
                    "is_risk_knowledge_related": False
                }
            elif active_mode == "risk_knowledge_node":
                return {
                    "output": "",
                    "conversation_history": conversation_history,
                    "risk_context": risk_context,
                    "user_data": user_data,
                    "active_mode": "risk_knowledge_node",
                    "risk_generation_requested": False,
                    "risk_register_requested": False,
                    "matrix_recommendation_requested": False,
                    "is_risk_knowledge_related": True
                }
        
        # LLM-based classification for new queries
        system_prompt = """
You are the Risk Intent Router. Analyze the user's query and return ONLY a JSON object with the routing decision.

Output Format (strict JSON only):
{
  "intent": "<routing_decision>",
  "rationale": "<brief explanation>",
  "confidence": <0.0-1.0>
}

Available Risk Nodes (mutually exclusive):
1. **risk_register** - For searching/finding existing risks
   - Keywords: "show", "find", "list", "filter", "search", "existing risks"
   - Examples: "Find high-impact cybersecurity risks", "Show operational risks"

2. **risk_generation** - For creating/generating new risks  
   - Keywords: "generate", "create", "spin up", "produce", "new risks"
   - Examples: "Generate 10 risks", "Create risks for my organization"

3. **matrix_recommendation** - For risk matrix recommendations (matrix will directly be generated.)
   - Keywords: "3x3", "4x4", "5x5", "matrix", "scale", "scales", "recommend matrix"
   - Examples: "Recommend a 4x4 matrix", "Show risk matrix", "matrix scales"

4. **risk_knowledge** - For risk/matrix information, analysis and general queries. 
   - Keywords: "categories", "likelihood", "impact", "scoring", "appetite", "tolerance", "framework"
   - Examples: "What are my risk categories?", "Explain likelihood scales"

Decision Priority:
Understand the user's intent and context and map it to the appropriate risk node. You should know the difference between a question and a statement. If the user's input is a question, it may indicate a need for information (risk_knowledge). If it's a command or request for action, it may indicate a need for risk_generation, risk_register, or matrix_recommendation.
"""
        
        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input)
        ]
        
        response = llm.invoke(messages)
        response_content = response.content.strip()
        
        # Parse the JSON response
        try:
            parsed = json.loads(response_content)
        except json.JSONDecodeError:
            print(f"Failed to parse routing JSON: {response_content}")
            # Default to risk_knowledge for unclear queries
            parsed = {
                "intent": "risk_knowledge",
                "rationale": "Defaulting to risk knowledge for unclear query",
                "confidence": 0.5
            }

        intent = (parsed.get("intent") or "").lower()
        print(f"Risk Router Decision: {intent} (confidence: {parsed.get('confidence', 0)})")

        # Route based on intent classification and set active_mode
        if intent == "risk_generation":
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "active_mode": "risk_generation_node",
                "risk_generation_requested": True,
                "risk_register_requested": False,
                "matrix_recommendation_requested": False,
                "is_risk_knowledge_related": False
            }
        elif intent == "risk_register":
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "active_mode": "risk_register_node",
                "risk_generation_requested": False,
                "risk_register_requested": True,
                "matrix_recommendation_requested": False,
                "is_risk_knowledge_related": False
            }
        elif intent == "matrix_recommendation":
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "active_mode": "matrix_recommendation_node",
                "risk_generation_requested": False,
                "risk_register_requested": False,
                "matrix_recommendation_requested": True,
                "is_risk_knowledge_related": False
            }
        elif intent == "risk_knowledge":
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "active_mode": "risk_knowledge_node",
                "risk_generation_requested": False,
                "risk_register_requested": False,
                "matrix_recommendation_requested": False,
                "is_risk_knowledge_related": True
            }
        else:
            # Default to risk knowledge for unknown intents
            return {
                "output": "",
                "conversation_history": conversation_history,
                "risk_context": risk_context,
                "user_data": user_data,
                "active_mode": "risk_knowledge_node",
                "risk_generation_requested": False,
                "risk_register_requested": False,
                "matrix_recommendation_requested": False,
                "is_risk_knowledge_related": True
            }
            
    except Exception as e:
        print(f"Error in risk_node router: {str(e)}")
        # Default to risk knowledge on error
        return {
            "output": "",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "active_mode": "risk_knowledge_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
            "is_risk_knowledge_related": True
        }

# 3. Define the risk generation node
def risk_generation_node(state: LLMState):
    """Generate organization-specific risks based on user data and risk profiles"""
    print("Risk Generation Node Activated")
    print(f"Input received: {state.get('input', 'No input')}")
    try:
        user_data = state.get("user_data", {})
        organization_name = user_data.get("organization_name", "the organization")
        location = user_data.get("location", "the current location")
        domain = user_data.get("domain", "the industry domain")
        conversation_history = state.get("conversation_history", [])
        user_input = state["input"]

        print(f"🔍 Risk Generation Node - Full user_data: {user_data}")
        print(f"🔍 Available user_id fields: username='{user_data.get('username', 'NOT_FOUND')}', user_id='{user_data.get('user_id', 'NOT_FOUND')}'")
        print(f"User data: organization={organization_name}, location={location}, domain={domain}")
        
        model = get_llm()

        # System prompt for the risk generation agent that uses tools
        user_id = user_data.get('username', '') or user_data.get('user_id', '') or 'default_user'
        system_prompt = f"""
You are an expert Risk Management Specialist that generates organization-specific risks.

CONTEXT:
- Current user ID: "{user_id}"
- Current user's organization: "{organization_name}"
- Location: "{location}" 
- Domain: "{domain}"

PROCESS:
1) First, call the get_risk_profiles tool with user_id="{user_id}" to retrieve the user's risk framework and scales
2) Use the profile data to understand their risk categories and scale definitions
3) Generate risks according to the exact format specified below

AFTER GETTING RISK PROFILES:
From the user's message, infer:
• risk_count (how many risks to generate)  
• target organization name (if they specify a different org than the profile)  
• target location (if specified)  
• target domain/industry (if specified)  
• any category focus (keywords like "privacy", "security", "operational", etc.)

If any of the above are NOT provided in the user's message, FALL BACK to the profile values.
Determine risk_count from USER_MESSAGE if stated; otherwise default to 10. Cap at 20.

CATEGORIES (use these exact values):
["Competition","External","Financial","Innovation","Internal","Legal and Compliance","Operational","Project Management","Reputational","Safety","Strategic","Technology"]

Map user focuses to these categories:
- privacy, GDPR, HIPAA → Legal and Compliance
- security, cybersecurity → Technology
- outage, continuity → Operational
- brand, reputation → Reputational
- project, schedule → Project Management
- budget, cash flow → Financial
- innovation, R&D → Innovation
- people, talent, HR → Internal
- health, workplace safety → Safety
- competitor, market share → Competition
- geopolitics, climate → External
- strategy, mergers → Strategic

OUTPUT FORMAT — STRICT:
Return ONLY a single JSON object with this exact schema (no prose, no markdown, no code fences):
{{
  "risks": [
    {{
      "description": "Clear, specific risk description tailored to the organization",
      "category": "One of the allowed categories above",
      "likelihood": "One of the likelihood levels from user's risk profile",
      "impact": "One of the impact levels from user's risk profile",
      "treatment_strategy": "Concrete, actionable mitigation or management steps"
    }}
  ]
}}

REQUIREMENTS:
- The "risks" array length MUST equal the inferred risk_count (default 10)
- "likelihood" MUST be exactly one of the profile's likelihood level titles
- "impact" MUST be exactly one of the profile's impact level titles
- Make every risk specific to the final resolved organization, location, and domain
- Vary categories unless user explicitly narrows focus
- Ensure valid, parseable JSON
"""

        # Build conversation history
        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for turn in recent_history:
            if turn.get("user"):
                messages.append(HumanMessage(content=turn["user"]))
            if turn.get("assistant"):
                messages.append(AIMessage(content=turn["assistant"]))
        messages.append(HumanMessage(content=user_input))

        # Use create_react_agent with risk profile tool
        agent = create_react_agent(
            model=model,
            tools=[get_risk_profiles]
        )

        print("Generating risks...")
        result = agent.invoke({"messages": messages})
        final_msg = result["messages"][-1]
        response_content = getattr(final_msg, "content", getattr(final_msg, "text", "")) or ""
        
        print(f"LLM Response received: {response_content[:100]}...")
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_content}
        ]
        
        # Update risk context to include generated risks
        risk_context = state.get("risk_context", {})
        risk_context["generated_risks"] = True
        risk_context["organization"] = organization_name
        risk_context["industry"] = domain
        risk_context["location"] = location
        
        print("Risk generation completed successfully")
        return {
            "output": response_content,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "active_mode": "risk_generation_node",
            "risk_generation_requested": False  # Reset the flag
        }
    except Exception as e:
        print(f"Error in risk_generation_node: {str(e)}")
        traceback.print_exc()
        
        error_risk_context = state.get("risk_context", {})
        
        return {
            "output": f"I apologize, but I encountered an error while generating risks for your organization: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": error_risk_context,
            "active_mode": "risk_generation_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False
        }

def risk_register_node(state: LLMState):
    """
    Open the risk register, and when the user asks to find/filter risks,
    perform semantic search via a single LLM tool-calling flow. The LLM
    will (1) decide whether to call the tool and (2) compose the final
    natural-language reply from the tool results.
    """
    print("Risk Register Node Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", []) or []
        risk_context = state.get("risk_context", {}) or {}
        user_data = state.get("user_data", {}) or {}
        user_id = user_data.get("username", "") or user_data.get("user_id", "") or ""

        model = get_llm()

        system_prompt = f"""
You are the Risk Register assistant.

Your job is to help the user search, list, filter, or sort risks **from their finalized risk register**.

TOOL USE:
- If the user asks to **find/search/list/filter/sort** risks, you MUST call the tool `semantic_risk_search`.
- Always include:
  - query: a concise reformulation of the user's ask (defaults to the user's latest message if unspecified)
  - user_id: "{user_id}" (use this value when missing)
  - top_k: choose 5–10 based on query breadth (default 5)

AFTER THE TOOL RETURNS:
- Read the tool results and produce a clear, helpful natural-language response.
- Summarize what was found and why it matches.
- If results exist, present 3–5 best hits with key fields (e.g., category, description, department, owner) in a readable format.
- If no results, suggest alternative terms/broader queries.
- Do NOT dump raw JSON.

IF NO SEARCH IS REQUESTED:
- If the user only says things like "open my risk register", do NOT call the tool.
- Briefly confirm it's open and explain how to ask search queries (e.g., “find cyber risks about ransomware”).
        """.strip()

        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for turn in recent_history:
            if turn.get("user"):
                messages.append(HumanMessage(content=turn["user"]))
            if turn.get("assistant"):
                messages.append(AIMessage(content=turn["assistant"]))

        messages.append(HumanMessage(content=user_input))

        bound = model.bind_tools([semantic_risk_search])

        max_steps = 3 
        step = 0
        final_ai_msg = None

        while step < max_steps:
            step += 1
            ai_msg = bound.invoke(messages)
            tool_calls = getattr(ai_msg, "tool_calls", None)

            if not tool_calls:
                final_ai_msg = ai_msg
                break

            tool_messages = []
            for tc in tool_calls:
                name = tc.get("name")
                args = tc.get("args", {}) or {}
                call_id = tc.get("id")

                if name == "semantic_risk_search":
                    args.setdefault("user_id", user_id)
                    args.setdefault("top_k", 5)
                    if not args.get("query"):
                        args["query"] = user_input

                    try:
                        if hasattr(semantic_risk_search, "invoke"):
                            tool_result = semantic_risk_search.invoke(args)
                        else:
                            tool_result = semantic_risk_search(**args)
                    except Exception as tool_err:
                        tool_result = {"error": f"semantic_risk_search failed: {tool_err}"}

                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=call_id,
                            content=json.dumps(tool_result)
                        )
                    )
                else:
                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=call_id,
                            content=json.dumps({"error": f"Unknown tool '{name}'"})
                        )
                    )

            messages = messages + [ai_msg] + tool_messages

        if final_ai_msg is None:
            final_text = (
                "I’ve opened your risk register. You can ask me to search it, e.g., "
                "“find cyber risks about ransomware” or “show data privacy risks with high impact.”"
            )
        else:
            if isinstance(final_ai_msg.content, str):
                final_text = final_ai_msg.content.strip()
            else:
                try:
                    final_text = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in (final_ai_msg.content or [])
                    ).strip()
                except Exception:
                    final_text = "Here’s what I found in your risk register."

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
        

        return {
            "output": final_text,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "risk_register_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False
        }

    except Exception as e:
        error_response = (
            "I understand you want to access your risk register. I’ve opened it. "
            "You can ask me to search it with natural language (e.g., “find high-impact third-party risks”)."
        )
        error_risk_context = state.get("risk_context", {})
        
        return {
            "output": error_response,
            "conversation_history": (state.get("conversation_history", []) or []) + [
                {"user": state.get("input", ""), "assistant": error_response}
            ],
            "risk_context": error_risk_context,
            "user_data": state.get("user_data", {}),
            "active_mode": "risk_register_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False
        }

# 5. Define the matrix recommendation node
def matrix_recommendation_node(state: LLMState):
    print("Matrix Recommendation Node Activated")
    try:

        user_input   = state.get("input", "")
        user_data    = state.get("user_data", {}) or {}
        risk_context = state.get("risk_context", {}) or {}
        conversation_history = state.get("conversation_history", [])

        allowed_sizes = {"3x3", "4x4", "5x5"}
        matrix_size = state.get("matrix_size", "5x5")
        if matrix_size not in allowed_sizes:
            matrix_size = "5x5"

        # Profile defaults
        org = user_data.get("organization_name", "your organization")
        loc = user_data.get("location", "your location")
        dom = user_data.get("domain", "your industry")

        llm = get_llm()

        # ---------- Helpers ----------
        def _snap_size(size_str: str, default_: str = "5x5") -> str:
            try:
                r, c = [int(x) for x in size_str.lower().split("x")]
                avg = (r + c) / 2.0
                return "3x3" if avg <= 3.5 else "4x4" if avg <= 4.5 else "5x5"
            except Exception:
                return default_

        def _rc(size_str: str) -> tuple[int, int]:
            r, c = [int(x) for x in size_str.split("x")]
            return r, c

        def _ensure_levels(levels: list, count: int, base_titles: list[str]) -> list:
            """Trim or pad to exactly 'count' items with simple placeholders if needed."""
            levels = (levels or [])[:count]
            while len(levels) < count:
                i = len(levels) + 1
                levels.append({"level": i, "title": base_titles[min(i-1, len(base_titles)-1)], "description": "Contextual description"})
            # normalize level numbering
            for i, lv in enumerate(levels, 1):
                lv["level"] = i
                lv.setdefault("title", base_titles[min(i-1, len(base_titles)-1)])
                lv.setdefault("description", "Contextual description")
            return levels

        # Get user's existing risk profiles to include all their risk categories
        existing_risk_categories = []
        username = user_data.get("username", "")
        if username:
            profiles_result = RiskProfileDatabaseService.get_user_risk_profiles(username)
            if profiles_result.success and profiles_result.data and profiles_result.data.get("profiles"):
                existing_profiles = profiles_result.data.get("profiles", [])
                existing_risk_categories = [profile.get("riskType", "") for profile in existing_profiles if profile.get("riskType")]
        
        # If no existing profiles, use default comprehensive set
        if not existing_risk_categories:
            existing_risk_categories = [
                "Strategic Risk", "Operational Risk", "Financial Risk", "Compliance Risk",
                "Reputational Risk", "Health and Safety Risk", "Environmental Risk", "Technology Risk",
                "Cybersecurity Risk", "Supply Chain Risk", "Market Risk", "Regulatory Risk"
            ]
        
        # Create a simpler template for the LLM to follow
        risk_categories_list = ",\n    ".join([
            f'"{category}"' for category in existing_risk_categories
        ])

        # Enhanced prompt with better query understanding and category-specific scales
        prompt = f"""
You are a Risk Management Specialist creating customized risk matrices.

GOAL
Parse the user's request and return a tailored risk matrix as VALID JSON (no prose, no markdown).

CONTEXT ANALYSIS
- USER_MESSAGE: "{user_input}"
- CONVERSATION_HISTORY: Available for context about "my organization"
- PROFILE_DEFAULTS: organization="{org}", location="{loc}", domain="{dom}"
- EXISTING_RISK_CATEGORIES: {len(existing_risk_categories)} categories from user's profile

QUERY PARSING RULES
1) **Organization Resolution**:
   - If USER_MESSAGE mentions specific org (e.g., "hospital", "bank", "TechCorp") -> use that
   - If USER_MESSAGE says "my organization/company" -> use PROFILE_DEFAULTS organization
   - If no org mentioned -> use PROFILE_DEFAULTS organization

2) **Location Resolution**:
   - If USER_MESSAGE mentions location (e.g., "India", "London", "Mumbai") -> use that
   - If says "my" -> use PROFILE_DEFAULTS location
   - If no location -> use PROFILE_DEFAULTS location

3) **Domain/Industry Resolution**:
   - If USER_MESSAGE mentions industry (e.g., "hospital" -> healthcare, "bank" -> financial) -> map to domain
   - If says "my" -> use PROFILE_DEFAULTS domain
   - Common mappings: hospital->healthcare, bank->financial, startup->technology, manufacturing->manufacturing

4) **Matrix Size Resolution**:
   - Extract explicit size: "3x3", "4x4", "5x5", "3 by 3", etc.
   - If other size mentioned -> choose nearest (3x3, 4x4, or 5x5)
   - If no size -> default to "5x5"

CRITICAL REQUIREMENT: CATEGORY-SPECIFIC DESCRIPTIONS
For each risk category, you MUST generate UNIQUE likelihood and impact descriptions that are:
- Specific to that risk category type (e.g., "Strategic Risk" vs "Operational Risk")
- Tailored to the organization context (org, location, domain)
- Different from other categories (no generic descriptions)

Examples of category-specific descriptions:
- **Strategic Risk**: "Market disruption affecting long-term business strategy"
- **Operational Risk**: "Process failure impacting daily operations"
- **Financial Risk**: "Revenue loss or cost overrun affecting profitability"
- **Technology Risk**: "System outage or security breach affecting IT operations"
- **Compliance Risk**: "Regulatory violation resulting in penalties or legal action"

OUTPUT REQUIREMENTS
- JSON ONLY (no markdown, no explanations)
- Each risk category MUST have unique likelihood and impact descriptions
- Descriptions should be specific to the risk category AND organization context
- Include ALL {len(existing_risk_categories)} risk categories listed below

EXAMPLE MAPPINGS
- "recommend 3x3 matrix for hospital in India" -> org="hospital", location="India", domain="healthcare", size="3x3"
- "4x4 matrix for my organization" -> org=PROFILE_DEFAULTS, location=PROFILE_DEFAULTS, domain=PROFILE_DEFAULTS, size="4x4"
- "matrix for TechCorp startup in London" -> org="TechCorp", location="London", domain="technology", size="5x5" (default)

OUTPUT SCHEMA:
{{
  "matrix_data": {{
    "context": {{
      "organization_name": "...",
      "location": "...",
      "domain": "...",
      "matrix_size": "3x3|4x4|5x5"
    }},
    "risk_categories": [
      {{
        "riskType": "Strategic Risk",
        "definition": "Context-specific definition for Strategic Risk in the organization",
        "likelihoodScale": [
          {{"level": 1, "title": "Rare", "description": "Strategic risk-specific description for level 1"}},
          {{"level": 2, "title": "Unlikely", "description": "Strategic risk-specific description for level 2"}},
          {{"level": 3, "title": "Possible", "description": "Strategic risk-specific description for level 3"}},
          {{"level": 4, "title": "Likely", "description": "Strategic risk-specific description for level 4"}},
          {{"level": 5, "title": "Almost Certain", "description": "Strategic risk-specific description for level 5"}}
        ],
        "impactScale": [
          {{"level": 1, "title": "Minor", "description": "Strategic risk-specific impact description for level 1"}},
          {{"level": 2, "title": "Moderate", "description": "Strategic risk-specific impact description for level 2"}},
          {{"level": 3, "title": "Major", "description": "Strategic risk-specific impact description for level 3"}},
          {{"level": 4, "title": "Severe", "description": "Strategic risk-specific impact description for level 4"}},
          {{"level": 5, "title": "Critical", "description": "Strategic risk-specific impact description for level 5"}}
        ]
      }}
    ]
  }},
  "response_text": "A comprehensive, engaging response explaining the matrix recommendation. Include emojis, formatting, and context-appropriate language. Explain what was created, highlight key features, and provide next steps. Be conversational and helpful."
}}

REQUIRED RISK CATEGORIES TO INCLUDE:
{risk_categories_list}

For each risk category above, create a complete entry with:
- riskType: The exact category name
- definition: Context-specific definition for that risk type
- likelihoodScale: 5 levels with unique descriptions specific to that risk category
- impactScale: 5 levels with unique descriptions specific to that risk category

IMPORTANT: 
1. Include ALL {len(existing_risk_categories)} risk categories listed above
2. Each category MUST have unique, category-specific likelihood and impact descriptions
3. Do not use generic descriptions that are the same across categories
4. Make descriptions specific to the risk category type and organization context
""".strip()

        # ---------- LLM call ----------
        content = make_llm_call_with_history(prompt, user_input, conversation_history).strip()

        # ---------- Extract & validate JSON with LLM-generated response ----------
        response_text = ""
        try:
            # Best-effort JSON extraction
            start = content.find("{")
            end = content.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError("No JSON found in LLM response.")
            parsed_response = json.loads(content[start:end])
            
            # Extract matrix data and response text from LLM response
            matrix_data = parsed_response.get("matrix_data", {})
            response_text = parsed_response.get("response_text", "Matrix recommendation created successfully.")
            
            # If old format (direct matrix data), handle backwards compatibility
            if not matrix_data and parsed_response.get("context"):
                matrix_data = parsed_response
                response_text = "Matrix recommendation created successfully."

            # Resolve context with fallbacks
            ctx = matrix_data.get("context", {}) if isinstance(matrix_data, dict) else {}
            resolved_org  = ctx.get("organization_name") or org
            resolved_loc  = ctx.get("location") or loc
            resolved_dom  = ctx.get("domain") or dom
            resolved_size = ctx.get("matrix_size") or matrix_size
            if resolved_size not in allowed_sizes:
                resolved_size = _snap_size(resolved_size, matrix_size)

            R, C = _rc(resolved_size)

            # Process risk categories with individual scales
            risk_categories = matrix_data.get("risk_categories", [])
            processed_categories = []
            
            for category in risk_categories:
                # Ensure each category has proper likelihood and impact scales
                likelihood_scale = _ensure_levels(
                    category.get("likelihoodScale", []), 
                    R, 
                    ["Rare","Unlikely","Possible","Likely","Almost Certain"]
                )
                impact_scale = _ensure_levels(
                    category.get("impactScale", []), 
                    C, 
                    ["Minor","Moderate","Major","Severe","Critical"]
                )
                
                processed_category = {
                    "riskType": category.get("riskType", "Unknown Risk"),
                    "definition": category.get("definition", "Risk definition"),
                    "likelihoodScale": likelihood_scale,
                    "impactScale": impact_scale,
                    "matrixSize": resolved_size
                }
                processed_categories.append(processed_category)

            matrix_data["context"] = {
                "organization_name": resolved_org,
                "location": resolved_loc,
                "domain": resolved_dom,
                "matrix_size": resolved_size,
            }
            matrix_data["risk_categories"] = processed_categories[:10]  # cap to 10

            # Persist in risk_context
            risk_context["generated_matrix"] = matrix_data
            risk_context["matrix_size"] = resolved_size
            risk_context["organization"] = resolved_org
            risk_context["location"] = resolved_loc
            risk_context["industry"] = resolved_dom
            
            matrix_size = resolved_size

        except Exception as e:
            print(f"Matrix JSON parse warning: {e}")
            response_text = (
                f"I've created a {matrix_size} risk matrix framework. "
                "The risk profile dashboard will show you the standard risk categories with customizable scales."
            )

        # ---------- Conversation history ----------
        history = state.get("conversation_history", [])
        history.append({"user": user_input, "assistant": response_text})

        # ---------- Return (unchanged shape/flags) ----------
        return {
            "output": response_text,
            "conversation_history": history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "matrix_recommendation_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": True,
            "matrix_size": matrix_size,
        }

    except Exception as e:
        print(f"Error in matrix_recommendation_node: {str(e)}")
        traceback.print_exc()
        
        error_risk_context = state.get("risk_context", {})
        
        return {
            "output": f"I apologize, but I encountered an error while creating the matrix recommendation: {str(e)}. I'll create a standard {state.get('matrix_size', '5x5')} framework for you instead.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": error_risk_context,
            "user_data": state.get("user_data", {}),
            "active_mode": "matrix_recommendation_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
        }

def risk_knowledge_node(state: LLMState):
    """
    Specialized node for risk-related knowledge queries.
    Handles user risk profiles, risk analysis, and risk-specific information.
    Uses risk-specific tools: get_risk_profiles, semantic_risk_search
    """
    print("Risk Knowledge Node Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})
        user_id = user_data.get('username', '') or user_data.get('user_id', '') or 'default_user'

        model = get_llm()

        system_prompt = f"""
You are a **Risk Management Knowledge Specialist** with deep expertise in organizational risk management.  
Your role is to answer user questions about risks, their organization's risk framework, and provide actionable insights.  
Be conversational, helpful, and concise — ask clarifying questions when user input is vague.

---

### USER CONTEXT
Current User ID: "{user_id}"
Organization: "{user_data.get('organization_name', 'Unknown')}"  
Location: "{user_data.get('location', 'Unknown')}"  
Domain: "{user_data.get('domain', 'Unknown')}"

---

### AVAILABLE TOOLS

1. **get_risk_profiles**  
   Use this when users ask about:  
   - Risk categories, likelihood/impact scales, definitions  
   - How risks are assessed in their organization  
   - Their risk framework, methodology, or matrix  

2. **semantic_risk_search**  
   Use this when users want:  
   - To find/search specific risks from their finalized risk register  
   - To filter risks by category, impact, likelihood  
   - To view high-risk or specific thematic risks (e.g., cybersecurity, compliance)  

---

### EXPERTISE
You are capable of:
- Explaining risk assessment frameworks and categories  
- Analyzing and interpreting risk registers  
- Giving practical recommendations and risk treatment strategies  
- Explaining likelihood/impact scales and risk scoring  

---

### RESPONSE STRATEGY

1. **Understand Intent First:**  
   - If user is asking about their risk framework → use `get_risk_profiles`.  
   - If user is asking to find specific risks → use `semantic_risk_search`.  
   - If user is asking for analysis or recommendations → combine tool outputs with your own expertise.  

2. **Be Context-Aware:**  
   - Use the organization, location, and domain provided.  
   - If unclear, politely ask for clarification (e.g., "Do you want me to search your finalized risks or explain your risk framework?").  

3. **Provide Actionable Insights:**  
   - After using tools, summarize results in plain language.  
   - Add interpretation, highlight important risks, and suggest next steps where relevant.  

4. **Stay Conversational:**  
   - Keep responses user-friendly, avoid dumping raw JSON unless specifically requested.  
   - You may format results in a clean, structured way (bullet points, tables).  

---

### FEW-SHOT EXAMPLES

**Example 1:**  
**User:** "What are my risk categories?"  
**Action:** Call `get_risk_profiles`, extract categories, explain briefly what each means.  

**Example 2:**  
**User:** "Find all high-impact cybersecurity risks."  
**Action:** Call `semantic_risk_search` with filters (high-impact + cybersecurity), summarize results, and highlight key takeaways.  

**Example 3:**  
**User:** "Explain my risk framework."  
**Action:** Call `get_risk_profiles`, describe likelihood/impact scales, risk matrix, and categories in plain language.  

**Example 4:**  
**User:** "Do we have any operational risks above medium level?"  
**Action:** Call `semantic_risk_search` with operational + medium/high filters, summarize findings.  

---

Always try to **combine tool outputs with expert reasoning** to deliver meaningful insights.
"""

        # Build conversation history
        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for turn in recent_history:
            if turn.get("user"):
                messages.append(HumanMessage(content=turn["user"]))
            if turn.get("assistant"):
                messages.append(AIMessage(content=turn["assistant"]))
        messages.append(HumanMessage(content=user_input))

        # Use create_react_agent with ONLY get_risk_profiles (tool isolation)
        agent = create_react_agent(
            model=model,
            tools=[get_risk_profiles]
        )

        result = agent.invoke({"messages": messages})
        final_msg = result["messages"][-1]
        final_text = getattr(final_msg, "content", getattr(final_msg, "text", "")) or (
            "I can help you with risk-related questions using your risk profiles and register data. "
            "Ask me about your risk framework, categories, or search for specific risks."
        )

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
        

        return {
            "output": final_text,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "risk_knowledge_node"
        }

    except Exception as e:
        error_response = (
            "I apologize, but I encountered an error while processing your risk knowledge query. "
            "Please ask me about your risk profiles, risk categories, or search for specific risks."
        )
        error_risk_context = state.get("risk_context", {})
        
        return {
            "output": error_response,
            "conversation_history": (state.get("conversation_history", []) or []) + [
                {"user": state.get("input", ""), "assistant": error_response}
            ],
            "risk_context": error_risk_context,
            "user_data": state.get("user_data", {}),
            "active_mode": "risk_knowledge_node"
        }

