import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import MessagesState, START
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient
# from rag_tools import semantic_risk_search
from typing_extensions import TypedDict
from typing import List, Dict, Any
from dependencies import get_llm
import json
from knowledge_base import ISO_27001_KNOWLEDGE
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
        
        # LLM-based intent router for Risk Node
        system_prompt = """
You are the **Risk Node Intent Router**. Your job is to infer the user's **single best intent** (semantic intent, not keywords), extract normalized slots, and return **only** one JSON object in the exact format below—no extra text, no markdown, no code fences.

### Output (strict)
{
  "intent": "<one_of_intents>",
  "slots": { },
  "rationale": "<brief one-sentence why>",
  "confidence": <0.0-1.0>,
  "clarifying_question": "<only include if intent='clarify'>"
}

### Allowed intents
- generate_risks — create a set of risks given org/location/domain/total.
- update_preferences — update persistent preferences (risk profiles, scales, matrix size).
- view_risk_profile — open the risk profile dashboard/table view.
- view_risk_register — open the risk register/finalized risks view and handle search/filter queries.
- preview_matrix — show likelihood-impact matrix recommendation/preview.
- clarify — ask one focused question when essential info is missing or multiple intents are equally plausible.

### Slot schema & normalization (populate only what’s present)
- organization_name: string (e.g., "Acme Bank", "fintech startup")
- location: string (prefer "City, Country" if given; else region/country)
- domain: canonical string from { "cybersecurity","operational","financial","strategic","compliance","privacy","supply_chain","manufacturing","cloud","data","physical_security","it","enterprise" }. Map synonyms (e.g., "infosec"→"cybersecurity", "ops"→"operational").
- total: integer (e.g., 25)
- matrix_size: string "NxN" (e.g., "4x4","5x5")
- risk_profiles: array of strings (e.g., ["strategic","operational"])
- scales: object { "likelihood": "1-5" | "1-7", "impact": "1-5" | "1-7" }
- effective_date: ISO 8601 date if specified (YYYY-MM-DD)
- filters: object for view intents (e.g., {"region":"APAC","status":"finalized"})

Normalize numbers (e.g., "twenty"→20), dates (to ISO 8601), casing (title case for orgs/locations), and synonyms.

### Decision rules (precision first)
1. **Prefer action over Q&A** when the user asks to *do* something (generate/show/open/recommend/change).
2. If **essential slots** for an action are missing or **multiple intents** are equally likely → use `clarify` and ask **one** targeted, closed question that names the missing piece(s).
3. If the user asks to **change defaults/settings** (scales, matrix, profiles, default counts) → `update_preferences`.
4. “Open/Show/View” the register → `view_risk_register`; the profile table → `view_risk_profile`.
5. “Recommend/Suggest/Pick a XxY matrix/heatmap” → `preview_matrix` (extract `matrix_size` if present).
6. If the user both *requests a view* and *requests generation*, **generation takes precedence** (`generate_risks`) unless the user explicitly says “don’t generate”.
7. Greetings, small talk, or broad vagueness (“make it safer”, “help me start”) → `clarify`.
8. Out-of-scope or generic knowledge questions (no actionable mapping) → `clarify` asking which action they want.

### Confidence rubric
- 0.85–1.00: Clear imperative with required slots or unambiguous view/update.
- 0.60–0.84: Some inference required; minor slot gaps but intent is clear.
- <0.60: Ambiguous or missing essential info → prefer `clarify`.

### Synonym & phrase mapping (non-exhaustive)
- risk register: {"register","log","finalized risks","approved list"} → view_risk_register
- risk profile: {"profile table","risk appetite profile","baseline profile"} → view_risk_profile (if viewing); update_preferences (if changing)
- matrix: {"heatmap","risk heat map","grid","4 by 4"} → preview_matrix (matrix_size="4x4")
- cybersecurity: {"infosec","security","cyber"} → "cybersecurity"
- operational: {"ops","operations"} → "operational"

### Few-shot examples

User: Generate an initial set of 25 cyber risks for a fintech in London.
{
  "intent": "generate_risks",
  "slots": {"organization_name": "fintech", "location": "London", "domain": "cybersecurity", "total": 25},
  "rationale": "Explicit creation request with domain, location, and count.",
  "confidence": 0.92
}

User: Show me the current risk profile table.
{
  "intent": "view_risk_profile",
  "slots": {},
  "rationale": "Direct request to view the profile table.",
  "confidence": 0.96
}

User: Open my risk register for APAC.
{
  "intent": "view_risk_register",
  "slots": {"filters": {"region": "APAC"}},
  "rationale": "Wants the finalized risks view, filtered by region.",
  "confidence": 0.93
}

User: Find me risks with high impact.
{
  "intent": "view_risk_register",
  "slots": {"filters": {"impact": "high"}},
  "rationale": "Searching for specific risks by impact level.",
  "confidence": 0.95
}

User: Show me all cybersecurity risks.
{
  "intent": "view_risk_register",
  "slots": {"filters": {"category": "cybersecurity"}},
  "rationale": "Filtering risks by category.",
  "confidence": 0.92
}

User: Recommend a 4x4 matrix for my startup.
{
  "intent": "preview_matrix",
  "slots": {"matrix_size": "4x4"},
  "rationale": "Asks for a matrix recommendation with size.",
  "confidence": 0.90
}

User: Switch our likelihood scale to 1-7 and keep impact at 1-5.
{
  "intent": "update_preferences",
  "slots": {"scales": {"likelihood": "1-7", "impact": "1-5"}},
  "rationale": "Explicit preference change to scales.",
  "confidence": 0.95
}

User: Set default matrix to 5x5 and use profiles strategic + operational.
{
  "intent": "update_preferences",
  "slots": {"matrix_size": "5x5", "risk_profiles": ["strategic","operational"]},
  "rationale": "Updates persistent defaults for matrix and profiles.",
  "confidence": 0.94
}

User: Spin up 15 risks for our hospital in Bangalore focusing on privacy.
{
  "intent": "generate_risks",
  "slots": {"organization_name": "hospital", "location": "Bangalore", "domain": "privacy", "total": 15},
  "rationale": "Creation request with org, location, domain, and count.",
  "confidence": 0.90
}

User: Show the heat map.
{
  "intent": "preview_matrix",
  "slots": {},
  "rationale": "Heat map refers to the matrix preview; size not specified.",
  "confidence": 0.75
}

User: Make it safer.
{
  "intent": "clarify",
  "slots": {},
  "rationale": "Underspecified; could be generate, preview, or update.",
  "confidence": 0.35,
  "clarifying_question": "Do you want me to generate new risks, open the profile/register view, or adjust preferences like matrix size or scales?"
}

User: Generate risks for my SaaS; use our standard scales.
{
  "intent": "generate_risks",
  "slots": {"organization_name": "SaaS"},
  "rationale": "Actionable creation request; scales reference existing prefs.",
  "confidence": 0.78
}

### Validation
- Output must be a single JSON object with exactly the specified keys.
- Include "clarifying_question" **only** when intent = "clarify".
- Do not include code fences, extra commentary, or additional fields.

"""

        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)

        content = response_content.strip()
        if content.startswith("```") and content.endswith("```"):
            # Strip code fences if model returned fenced JSON
            content = content.strip('`')
        
        # Attempt to extract JSON if wrapped
        try:
            parsed = json.loads(content)
        except Exception:
            # Try to find first JSON object in the response
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(content[start:end+1])
            else:
                parsed = {"intent": "clarify", "slots": {}, "rationale": "Unparseable response", "confidence": 0.0, "clarifying_question": "Could you rephrase your request?"}

        intent = (parsed.get("intent") or "").lower()
        slots = parsed.get("slots") or {}

        # Map intents to flags/nodes
        if intent == "generate_risks":
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
        if intent == "update_preferences":
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
        if intent == "view_risk_register":
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
        if intent == "view_risk_profile":
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
        if intent == "preview_matrix":
            matrix_size = slots.get("matrix_size") or slots.get("size")
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
                "matrix_size": matrix_size or "5x5"
            }

        # Clarify or fallback: respond with clarifying question if provided
        clarifying_question = parsed.get("clarifying_question") or "Could you clarify what you want to do regarding risks?"

        updated_history = conversation_history + [
            {"user": user_input, "assistant": clarifying_question}
        ]
        return {
            "output": clarifying_question,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False
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
    print(f"Input received: {state.get('input', 'No input')}")
    try:
        llm = get_llm()
        
        user_data = state.get("user_data", {})
        organization_name = user_data.get("organization_name", "the organization")
        location = user_data.get("location", "the current location")
        domain = user_data.get("domain", "the industry domain")
        risks_applicable = user_data.get("risks_applicable", [])
        conversation_history = state.get("conversation_history", [])

        print(f"User data: organization={organization_name}, location={location}, domain={domain}")
        
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
        
        print(f"Using likelihood scale: {default_likelihood}")
        print(f"Using impact scale: {default_impact}")
        
        # Create a comprehensive prompt for risk generation
        risk_generation_prompt = f"""
You are an expert Risk Management Specialist.

You will receive:
1) The user's message (their request).
2) Current user's organization:
   - organization_name: "{organization_name}"
   - location: "{location}"
   - domain: "{domain}"
3) User-preferred scales:
   - likelihood levels (exact strings): {default_likelihood}
   - impact levels (exact strings): {default_impact}

YOUR TASK
- From the user's message, infer:
  • risk_count (how many risks to generate)  
  • target organization name (if they specify a different org than the profile)  
  • target location (if specified)  
  • target domain/industry (if specified)  
  • any category focus (keywords like “privacy”, “security”, “operational”, etc.)
- If any of the above are NOT provided in the user's message, FALL BACK to the profile values.
- Determine risk_count from USER_MESSAGE if stated; otherwise default to 10. Cap at 50.
- Always generate specific, actionable, non-duplicative risks tailored to the final resolved context (org, location, domain, focus).

CATEGORIES
Use only the following category values for the "category" field:
["Competition","External","Financial","Innovation","Internal","Legal and Compliance","Operational","Project Management","Reputational","Safety","Strategic","Technology"]

If the user mentions topical focuses or synonyms, map them sensibly to the above categories. For example:
- privacy, data privacy, GDPR, HIPAA → Legal and Compliance
- security, cybersecurity, info-sec → Technology
- outage, continuity, downtime, incident response → Operational
- brand, reputation, PR → Reputational
- project, schedule, scope, delivery → Project Management
- budget, cash flow, fraud, credit → Financial
- innovation, R&D, emerging tech → Innovation
- people, talent, attrition, HR → Internal
- health, workplace safety → Safety
- competitor, market share → Competition
- geopolitics, climate, regulation changes → External
- strategy, mergers, market positioning → Strategic

OUTPUT FORMAT — STRICT
- Return ONLY a single JSON object with this exact schema and nothing else (no prose, no markdown, no code fences):
{{
  "risks": [
    {{
      "description": "Clear, specific risk description tailored to the organization",
      "category": "One of the allowed categories above",
      "likelihood": "One of the allowed likelihood levels",
      "impact": "One of the allowed impact levels",
      "treatment_strategy": "Concrete, actionable mitigation or management steps"
    }}
  ]
}}
- The "risks" array length MUST equal the inferred risk_count (default 10 if not stated).
- "likelihood" MUST be exactly one of the provided likelihood levels (string match).
- "impact" MUST be exactly one of the provided impact levels (string match).
- Do not add extra keys at any level. Do not include comments, explanations, or trailing commas.

QUALITY BAR
- Make every risk specific to the final resolved organization, location, and domain.
- Reflect location-specific regulations or standards when relevant.
- Vary categories and angles to avoid overlap unless the user explicitly narrows the focus.
- Ensure the JSON is valid and parseable.

INTERPRETATION EXAMPLES (do not echo in output)
- “Spin up 15 risks for our hospital in Bangalore focusing on privacy.” → 15 privacy-heavy, healthcare-specific risks, location=Bangalore, category bias=Legal and Compliance; use scales provided above.
- “Give 8 operational risks for ACME Bank in Mumbai” → 8 risks, category=Operational, org=ACME Bank, location=Mumbai, domain=Banking if implied; use scales.
- “List risks for my org” → default to profile org/location/domain and 10 risks.
"""

        print("Sending request to LLM...")
        response_content = make_llm_call_with_history(risk_generation_prompt, state["input"], conversation_history)
        print(f"LLM Response received: {response_content[:100]}...")  # First 100 chars only
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": state["input"], "assistant": response_content}
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
            "risk_generation_requested": False  # Reset the flag
        }
    except Exception as e:
        print(f"Error in risk_generation_node: {str(e)}")
        traceback.print_exc()
        return {
            "output": f"I apologize, but I encountered an error while generating risks for your organization: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False
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
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
        }

    except Exception as e:
        error_response = (
            "I understand you want to access your risk register. I’ve opened it. "
            "You can ask me to search it with natural language (e.g., “find high-impact third-party risks”)."
        )
        return {
            "output": error_response,
            "conversation_history": (state.get("conversation_history", []) or []) + [
                {"user": state.get("input", ""), "assistant": error_response}
            ],
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
        }


# def risk_register_node(state: LLMState):
#     """
#     Single-call tool-using node:
#     - Let create_react_agent orchestrate tool calls + final answer.
#     - No manual while-loop, no manual ToolMessage handling.
#     """
#     from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
#     from langgraph.prebuilt import create_react_agent

#     print("Risk Register Node Activated")
#     try:
#         user_input = state["input"]
#         conversation_history = state.get("conversation_history", []) or []
#         risk_context = state.get("risk_context", {}) or {}
#         user_data = state.get("user_data", {}) or {}
#         user_id = user_data.get("username", "") or user_data.get("user_id", "") or ""

#         model = get_llm()  # must support tool-calling

#         system_prompt = f"""
# You are the Risk Register assistant.

# - If the user asks to find/search/list/filter/sort risks from their finalized register,
#   call the tool `semantic_risk_search` with:
#     - query: a concise reformulation of the user's ask (fallback: latest user message)
#     - user_id: "{user_id}"
#     - top_k: 5–10 (default 5)

# After tool returns:
# - Write a concise, helpful summary using the results (no raw JSON).
# - If no results, suggest better queries.
# If the user just asks to open the register (no search), don't call the tool—just explain how to search.
# """.strip()

#         # Build short memory
#         messages = [SystemMessage(content=system_prompt)]
#         for turn in (conversation_history[-5:] if len(conversation_history) > 5 else conversation_history):
#             if turn.get("user"):
#                 messages.append(HumanMessage(content=turn["user"]))
#             if turn.get("assistant"):
#                 messages.append(AIMessage(content=turn["assistant"]))
#         messages.append(HumanMessage(content=user_input))

#         # Prebuilt agent handles the internal loop automatically
#         agent = create_react_agent(
#             model=model,                # you may also do: model.bind_tools([semantic_risk_search])
#             tools=[semantic_risk_search]
#             # recursion_limit=3,         # optional safety cap (see docs)
#         )

#         result = agent.invoke({"messages": messages})
#         final_msg = result["messages"][-1]
#         final_text = getattr(final_msg, "content", getattr(final_msg, "text", "")) or (
#             "I’ve opened your risk register. Ask me something like “find high-impact third-party risks.”"
#         )

#         updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
#         return {
#             "output": final_text,
#             "conversation_history": updated_history,
#             "risk_context": risk_context,
#             "user_data": user_data,
#             "risk_generation_requested": False,
#             "preference_update_requested": False,
#             "risk_register_requested": False,
#         }

#     except Exception:
#         error_response = (
#             "I’ve opened your risk register. You can ask me to search it, e.g., "
#             "“find cyber risks about ransomware.”"
#         )
#         return {
#             "output": error_response,
#             "conversation_history": (state.get("conversation_history", []) or []) + [
#                 {"user": state.get("input", ""), "assistant": error_response}
#             ],
#             "risk_context": state.get("risk_context", {}),
#             "user_data": state.get("user_data", {}),
#             "risk_generation_requested": False,
#             "preference_update_requested": False,
#             "risk_register_requested": False,
#         }


def preference_update_node(state: LLMState):
    """Handle user preference updates for risk profiles"""
    print("Preference Update Node Activated")
    try:
        llm = get_llm()

        user_input = state["input"]
        user_data = state.get("user_data", {})
        
        # Get username from user_data (assuming it's passed from main.py)
        username = user_data.get("username", "")
        
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
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "matrix_size": matrix_size,
        }

    except Exception as e:
        print(f"Error in matrix_recommendation_node: {str(e)}")
        traceback.print_exc()
        return {
            "output": f"I apologize, but I encountered an error while creating the matrix recommendation: {str(e)}. I'll create a standard {state.get('matrix_size', '5x5')} framework for you instead.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "user_data": state.get("user_data", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
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
   - Risk query, searching, filtering, and finding (e.g., "find risks with high impact", "show me cybersecurity risks", "list operational risks")
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

User: "Find me the risks related to data breach"
Intent: RISK-RELATED
Route to: risk_node

User: "Find me risks with high impact"
Intent: RISK-RELATED
Route to: risk_node

User: "Show me all cybersecurity risks"
Intent: RISK-RELATED
Route to: risk_node

User: "List operational risks with medium likelihood"
Intent: RISK-RELATED
Route to: risk_node

User: "Search for risks owned by John Smith"
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
    try:
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        routing_decision = response_content.strip().lower()
        
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


def knowledge_node(state: LLMState):
    """Node for handling ISO 27001 and information security knowledge-related queries"""
    print("Knowledge Node Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", [])
        risk_context = state.get("risk_context", {})
        user_data = state.get("user_data", {})

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
        
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)

        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_content}
        ]
        
        return {
            "output": response_content,
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
        "risk_generation_requested": False,
        "preference_update_requested": False,
        "risk_register_requested": False,
        "risk_profile_requested": False,
        "matrix_recommendation_requested": False,
        "is_audit_related": False,
        "is_risk_related": False
    }
    
    # Use thread_id for memory persistence within the session
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(state, config)
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