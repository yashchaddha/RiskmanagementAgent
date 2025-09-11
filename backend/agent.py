import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient
from typing_extensions import TypedDict
from typing import List, Dict, Any
from dependencies import get_llm
import json
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from database import RiskProfileDatabaseService
import traceback

# Load environment variables from .env
load_dotenv()

# Set up LangSmith project name
LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="make_llm_call_with_history")
def make_llm_call_with_history(system_prompt: str, user_input: str, conversation_history: list) -> str:
    """Standardized LLM call that includes conversation history for context"""
    llm = get_llm()
    
    # Build messages with conversation history for context
    messages = []
    
    # Add system message
    messages.append(SystemMessage(content=system_prompt))
    
    # Add conversation history as context (last 5 exchanges to avoid token limits)
    recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
    for exchange in recent_history:
        if exchange.get("user"):
            messages.append(HumanMessage(content=exchange["user"]))
        if exchange.get("assistant"):
            messages.append(AIMessage(content=exchange["assistant"]))
    
    # Add current user input
    messages.append(HumanMessage(content=user_input))
    
    # Make the call
    response = llm.invoke(messages)
    return response.content

@tool("get_risk_profiles")
def get_risk_profiles(user_id: str) -> dict:
    """
    Retrieve user's comprehensive risk profiles for intelligent risk generation.
    
    Args:
        user_id: User identifier
        
    Returns:
        Complete risk profile data including categories, scales, and definitions
    """
    print(f"🔍 get_risk_profiles called with user_id: '{user_id}'")
    try:
        print(f"🔍 Calling RiskProfileDatabaseService.get_user_risk_profiles('{user_id}')")
        result = RiskProfileDatabaseService.get_user_risk_profiles(user_id)
        
        if result.success and result.data and result.data.get("profiles"):
            profiles = result.data.get("profiles", [])
            print(f"🔍 Found {len(profiles)} profiles for user")
            
            # Extract useful data for risk generation
            risk_categories = []
            likelihood_scales = {}
            impact_scales = {}
            
            for profile in profiles:
                risk_type = profile.get("riskType", "")
                if risk_type:
                    risk_categories.append(risk_type)
                    
                    # Extract scales with descriptions
                    likelihood_scale = profile.get("likelihoodScale", [])
                    impact_scale = profile.get("impactScale", [])
                    
                    likelihood_scales[risk_type] = [
                        {"level": item.get("level"), "title": item.get("title"), "description": item.get("description", "")}
                        for item in likelihood_scale
                    ]
                    impact_scales[risk_type] = [
                        {"level": item.get("level"), "title": item.get("title"), "description": item.get("description", "")}
                        for item in impact_scale
                    ]
            
            print(f"🔍 Successfully extracted {len(risk_categories)} risk categories: {risk_categories}")
            return {
                "success": True,
                "risk_categories": risk_categories,
                "likelihood_scales": likelihood_scales,
                "impact_scales": impact_scales,
                "profiles_count": len(profiles),
                "user_id": user_id
            }
        
        print(f"🔍 No risk profiles found - returning error")
        return {
            "success": False,
            "error": "No risk profiles found",
            "risk_categories": [],
            "user_id": user_id
        }
        
    except Exception as e:
        print(f"🔍 Exception in get_risk_profiles: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "risk_categories": [],
            "user_id": user_id
        }


@tool("knowledge_base_search")
def knowledge_base_search(query: str, category: str = "all", top_k: int = 5) -> dict:
    """
    Search ISO 27001:2022 knowledge base for relevant clauses, controls, and information.
    Returns relevant entries from the knowledge base using semantic search.

    Args:
        query: User's question about ISO 27001 standards, clauses, or controls
        category: Filter by category - "clauses", "annex_a", or "all" (default)
        top_k: Number of results to return (default 5)
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vec: List[float] = emb.embed_query(query)
        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        
        OUTPUT_FIELDS = ["doc_id", "text"]
        
        # No filtering for now with simplified schema
        filter_expr = None
        
        results = client.search(
            collection_name="iso_knowledge_index",
            data=[query_vec],
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=filter_expr if filter_expr else None,
        )

        hits: List[Dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass

                hits.append({
                    "id": entity.get("doc_id"),
                    "text": entity.get("text"),
                    "score": score
                })

        return {
            "hits": hits,
            "count": len(hits),
            "query": query,
            "category": category
        }

    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "category": category}


@tool("semantic_risk_search")
def semantic_risk_search(query: str, user_id: str, top_k: int = 5) -> dict:
    """
    Semantically search the user's finalized risks stored in Zilliz/Milvus.
    Returns a JSON payload of the top matches (with scores) filtered by user_id.

    Args:
        query: Free-text user query about risks.
        user_id: Tenant scoping (strictly filter to this user).
        top_k: Number of results to return.
    """
    try:
        emb = OpenAIEmbeddings(model="text-embedding-3-small")
        query_vec: List[float] = emb.embed_query(query)
        client = MilvusClient(
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
            secure=True
        )
        OUTPUT_FIELDS = [
            "risk_id", "user_id", "organization_name", "location", "domain", 
            "category", "description", "likelihood", "impact", "treatment_strategy",
            "department", "risk_owner", "asset_value", "security_impact", 
            "target_date", "risk_progress", "residual_exposure", "risk_text"
        ]
        expr = f"user_id == '{user_id}'"
        results = client.search(
            collection_name="finalized_risks_index",
            data=[query_vec],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=expr,
        )

        hits: List[Dict[str, Any]] = []
        if results and len(results) > 0:
            for hit in results[0]:
                entity = hit.get("entity", {}) if isinstance(hit, dict) else getattr(hit, "entity", {})
                score = hit.get("score", None) if isinstance(hit, dict) else getattr(hit, "score", None)
                try:
                    score = float(score) if score is not None else None
                except Exception:
                    pass

                hits.append({
                    "risk_id": entity.get("risk_id"),
                    "score": score,
                    "user_id": entity.get("user_id"),
                    "organization_name": entity.get("organization_name"),
                    "location": entity.get("location"),
                    "domain": entity.get("domain"),
                    "category": entity.get("category"),
                    "description": entity.get("description"),
                    "likelihood": entity.get("likelihood"),
                    "impact": entity.get("impact"),
                    "treatment_strategy": entity.get("treatment_strategy"),
                    "department": entity.get("department"),
                    "risk_owner": entity.get("risk_owner"),
                    "asset_value": entity.get("asset_value"),
                    "security_impact": entity.get("security_impact"),
                    "target_date": entity.get("target_date"),
                    "risk_progress": entity.get("risk_progress"),
                    "residual_exposure": entity.get("residual_exposure"),
                    "risk_text": entity.get("risk_text"),
                })

        return {
            "hits": hits,
            "count": len(hits),
            "query": query,
            "user_id": user_id
        }

    except Exception as e:
        return {"hits": [], "count": 0, "error": str(e), "query": query, "user_id": user_id}


# 1. Define the state schema
class LLMState(TypedDict):
    input: str
    output: str
    conversation_history: list
    risk_context: dict  # Store risk assessment context
    user_data: dict  # Store user organization data
    active_mode: str  # Track current active node for stickiness
    risk_generation_requested: bool  # Flag to indicate if risk generation is needed
    risk_register_requested: bool  # Flag to indicate if risk register access is needed
    matrix_recommendation_requested: bool  # Flag to indicate if matrix recommendation is needed
    is_audit_related: bool  # Flag to indicate if query is audit-related
    is_risk_related: bool  # Flag to indicate if query is risk-related
    is_risk_knowledge_related: bool  # Flag to indicate if query is about risk knowledge/profiles

# 2. Define the risk node as an intent router with stickiness
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

def orchestrator_node(state: LLMState) -> LLMState:
    """Top-level orchestrator with deterministic prefilter and single-token output"""
    print("Orchestrator Activated")
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    user_data = state.get("user_data", {})
    active_mode = state.get("active_mode", "")
    
    # Deterministic prefilter BEFORE LLM
    user_text_lower = user_input.lower()
    user_text_len = len(user_input)
    
    # Stickiness check for short follow-ups in risk domain
    follow_up_keywords = ["filter", "sort", "only", "add", "exclude"]
    is_short_followup = user_text_len <= 80 and any(kw in user_text_lower for kw in follow_up_keywords)
    
    if active_mode.startswith("risk_") and is_short_followup:
        routing_decision = "risk_node"
    else:
        # Deterministic keyword-based routing
        audit_cues = ["audit", "auditor", "evidence", "audit plan"]
        risk_cues = ["risk", "risk register", "matrix", "3x3", "4x4", "5x5", "likelihood", "impact", "categories", "generate"]
        
        if any(cue in user_text_lower for cue in audit_cues):
            routing_decision = "audit_facilitator"
        elif any(cue in user_text_lower for cue in risk_cues):
            routing_decision = "risk_node"
        else:
            # Use LLM for edge cases
            system_prompt = """
You are a routing classifier. Output EXACTLY ONE token from: {knowledge_node, risk_node, audit_facilitator}

Rules:
- audit_facilitator: audit processes, audit findings, audit documentation
- risk_node: risk management, risk register, risk matrices, risk generation
- knowledge_node: ISO 27001, information security standards, compliance guidance

Output only the single token, no other text.
"""
            
            try:
                response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
                routing_decision = response_content.strip().lower()
            except Exception as e:
                print(f"Error in orchestrator LLM call: {e}")
                routing_decision = "knowledge_node"
    
    # Strict validation - accept only valid labels
    valid_labels = ["audit_facilitator", "risk_node", "knowledge_node"]
    if routing_decision not in valid_labels:
        # Fallback logic
        if any(kw in user_text_lower for kw in ["risk", "matrix", "likelihood", "impact"]):
            routing_decision = "risk_node"
        else:
            routing_decision = "knowledge_node"
    
    print(f"Orchestrator routing decision: {routing_decision}")
    
    # Set domain-level active_mode and routing flags
    if routing_decision == "audit_facilitator":
        return {
            "input": state["input"],
            "output": "",
            "conversation_history": conversation_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "audit_facilitator",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": True,
            "is_risk_related": False,
            "is_risk_knowledge_related": False
        }
    elif routing_decision == "risk_node":
        return {
            "input": state["input"],
            "output": "",
            "conversation_history": conversation_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "risk_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": True,
            "is_risk_knowledge_related": False
        }
    else:  # knowledge_node
        return {
            "input": state["input"],
            "output": "",
            "conversation_history": conversation_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "knowledge_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_risk_knowledge_related": False
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


def knowledge_node(state: LLMState):
    """
    Node for handling ISO 27001 and information security standards knowledge.
    Specialized for ISO/IEC 27001:2022 compliance and regulatory guidance.
    Uses RAG with knowledge_base_search tool.
    """
    print("Knowledge Node Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})

        model = get_llm()

        system_prompt = """
You are an ISO/IEC 27001:2022 assistant specializing in information security management systems.

TOOL USE:
- For ANY question about ISO 27001:2022 clauses, subclauses, Annex A controls, or related information security topics, call the `knowledge_base_search` tool.
- Use these parameters:
  - query: reformulate the user's question for effective search
  - category: "clauses" (for clauses/subclauses), "annex_a" (for controls), or "all" (general search)
  - top_k: 3-5 results (default 5)

RESPONSE STRATEGY:
1) **Specific queries** (e.g., "Clause 5.2", "A.8.24"):
   - Call tool with exact query and appropriate category
   - Present the specific clause/control information clearly
   - Include parent context when relevant

2) **General queries** (e.g., "leadership requirements", "cryptographic controls"):
   - Call tool with broader search terms
   - Synthesize information from multiple results
   - Provide comprehensive answers

3) **Unrelated queries**:
   - Don't call the tool
   - Politely redirect to ISO 27001 topics

AFTER TOOL RESULTS:
- Read the search results and provide accurate, helpful responses
- For specific clauses/controls: present the exact information found
- For general topics: synthesize multiple results into coherent answers
- If no relevant results: acknowledge and suggest alternative search terms
- NEVER invent information not found in the search results

FORMATTING:
- Use clear headings for clauses/controls (e.g., "**Clause 5.2: Information Security Policy**")
- Include descriptions and context from search results
- When presenting multiple items, use bullet points or numbered lists
- Always cite the source (clause number, control ID, etc.)
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

        # Use create_react_agent for simpler tool handling
        agent = create_react_agent(
            model=model,
            tools=[knowledge_base_search]
        )

        result = agent.invoke({"messages": messages})
        final_msg = result["messages"][-1]
        final_text = getattr(final_msg, "content", getattr(final_msg, "text", "")) or (
            "I'm specialized in ISO/IEC 27001:2022 compliance guidance. "
            "Please ask me questions about information security management systems, "
            "ISO 27001 clauses, Annex A controls, or related compliance topics."
        )

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
        

        return {
            "output": final_text,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "knowledge_node"
        }

    except Exception as e:
        error_response = (
            "I apologize, but I encountered an error while processing your information security query. "
            "Please ask me about ISO/IEC 27001:2022 clauses, Annex A controls, or related compliance topics."
        )
        error_risk_context = state.get("risk_context", {})
        
        return {
            "output": error_response,
            "conversation_history": (state.get("conversation_history", []) or []) + [
                {"user": state.get("input", ""), "assistant": error_response}
            ],
            "risk_context": error_risk_context,
            "user_data": state.get("user_data", {}),
            "active_mode": "knowledge_node"
        }

# 6. Build the graph with the state schema
builder = StateGraph(LLMState)
builder.add_node("orchestrator", orchestrator_node)
builder.add_node("risk_node", risk_node)
builder.add_node("risk_generation", risk_generation_node)
builder.add_node("risk_register", risk_register_node)
builder.add_node("matrix_recommendation", matrix_recommendation_node)
builder.add_node("knowledge_node", knowledge_node)
builder.add_node("risk_knowledge_node", risk_knowledge_node)
builder.set_entry_point("orchestrator")

# Add conditional routing from orchestrator (two-level funnel)
def orchestrator_routing(state: LLMState) -> str:
    if state.get("is_audit_related", False):
        return "risk_node"  # Temporary routing to risk_node until audit_facilitator is implemented
    elif state.get("is_risk_related", False):
        return "risk_node"
    else:
        return "knowledge_node"  # Default to ISO knowledge node

# Add conditional edge based on risk routing flags
def should_generate_risks(state: LLMState) -> str:
    """Route risk queries to appropriate specialized nodes"""
    if state.get("risk_generation_requested", False):
        return "risk_generation"
    elif state.get("risk_register_requested", False):
        return "risk_register"
    elif state.get("matrix_recommendation_requested", False):
        return "matrix_recommendation"
    elif state.get("is_risk_knowledge_related", False):
        return "risk_knowledge_node"
    return "end"

# Add orchestrator routing (two-level funnel)
builder.add_conditional_edges("orchestrator", orchestrator_routing, {
    "knowledge_node": "knowledge_node",  # Route to knowledge node for ISO 27001 related queries
    "risk_node": "risk_node"  # Route to risk sub-router for all risk-related queries
})

builder.add_conditional_edges("risk_node", should_generate_risks, {
    "risk_generation": "risk_generation",
    "risk_register": "risk_register",
    "matrix_recommendation": "matrix_recommendation",
    "risk_knowledge_node": "risk_knowledge_node",
    "end": END
})
builder.add_edge("risk_generation", END)
builder.add_edge("risk_register", END)
builder.add_edge("matrix_recommendation", END)
builder.add_edge("knowledge_node", END)
builder.add_edge("risk_knowledge_node", END)

# Add memory to the graph
memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

def run_agent(message: str, conversation_history: list = None, risk_context: dict = None, user_data: dict = None, thread_id: str = "default_session"):
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
        "active_mode": "",
        "risk_generation_requested": False,
        "risk_register_requested": False,
        "matrix_recommendation_requested": False,
        "is_audit_related": False,
        "is_risk_related": False,
        "is_risk_knowledge_related": False
    }
    
    # Use thread_id for memory persistence within the session
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(state, config)
    return result["output"], result["conversation_history"], result["risk_context"], result["user_data"]

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