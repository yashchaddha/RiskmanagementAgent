import os
import json
import traceback
from datetime import datetime
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_openai import OpenAIEmbeddings
from pymilvus import MilvusClient
from rag_tools import semantic_risk_search
from typing_extensions import TypedDict
from typing import List, Dict, Any
from dependencies import get_llm
from knowledge_base import ISO_27001_KNOWLEDGE
from langsmith import traceable
import uuid
from database import ControlsDatabaseService

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
            "category", "department", "risk_owner", "risk_text"
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
                    "department": entity.get("department"),
                    "risk_owner": entity.get("risk_owner"),
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

@tool("semantic_control_search")
def semantic_control_search(query: str, user_id: str, top_k: int = 5) -> dict:
    """
    Semantically search the user's controls stored in Zilliz/Milvus.
    Returns a JSON payload of the top matches (with scores) filtered by user_id.

    Args:
        query: Free-text user query about controls.
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
            "control_id", "control_title", "control_description", "annexA_map", "linked_risk_ids", "owner_role", "process_steps", "evidence_samples", "metrics", "frequency", "policy_ref", "status", "rationale", "assumptions", "user_id", "created_at", "updated_at"
        ]

        results = client.search(
            collection_name="controls_index",
            data=[query_vec],
            anns_field="embedding",
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter=f"user_id == '{user_id}'"
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
                    "control_id": entity.get("control_id"),
                    "control_title": entity.get("control_title"),
                    "control_description": entity.get("control_description"),
                    "annexA_map": entity.get("annexA_map"),
                    "linked_risk_ids": entity.get("linked_risk_ids"),
                    "owner_role": entity.get("owner_role"),
                    "process_steps": entity.get("process_steps"),
                    "evidence_samples": entity.get("evidence_samples"),
                    "metrics": entity.get("metrics"),
                    "frequency": entity.get("frequency"),
                    "policy_ref": entity.get("policy_ref"),
                    "status": entity.get("status"),
                    "rationale": entity.get("rationale"),
                    "assumptions": entity.get("assumptions"),
                    "user_id": entity.get("user_id"),
                    "created_at": entity.get("created_at"),
                    "updated_at": entity.get("updated_at"),
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
    is_control_related: bool
    is_knowledge_related: bool
    control_generation_requested: bool
    control_parameters: dict
    control_retrieved_context: dict
    generated_controls: list
    selected_controls: list
    pending_selection: bool
    control_session_id: str

    # New control-routing helpers
    control_target: str  # one of: generate_control_node | control_library_node | control_knowledge_node
    control_query: str
    control_filters: dict
    risk_description: str

# 2. Define the control node
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_node")
def control_node(state: LLMState) -> LLMState:
    """
    Conversational control intent classifier that routes to appropriate control sub-domain
    """
    print("Control Node Activated")
    
    user_input = state.get("input", "").strip()
    conversation_history = state.get("conversation_history", [])
    user_data = state.get("user_data", {})
    
    # Industry-standard prompt for control domain classification
    system_prompt = """# Control Management Assistant - Sub-Domain Classification

## Role
You are a conversational classifier within the Control Management domain. Your job is to understand user intent and either route to the appropriate control sub-domain or ask clarifying questions.

## Available Control Sub-Domains
1. **generate_control**: Creating new security controls for risks or requirements
2. **control_library**: Searching, viewing, and managing user's existing saved controls
3. **control_knowledge**: Educational information about control types, frameworks, and concepts

## Task
Analyze the user's query and determine the most appropriate action using semantic understanding.

## Decision Process
1. **Intent Analysis**: What is the user trying to accomplish?
   - **Creation/Generation**: "generate", "create", "develop", "design" controls
   - **Personal Data Access**: "show MY", "list MY", "find MY", "search MY" controls  
   - **Educational/Conceptual**: "what are", "explain", "tell me about", "how do" controls work

2. **Confidence Assessment**: Rate confidence (0.0-1.0) in understanding intent

3. **Action Decision**:
   - Confidence >= 0.8: Route to sub-domain
   - Confidence < 0.8: Ask clarifying questions

## Output Format
```json
{
  "action": "route" | "clarify",
  "sub_domain": "generate_control" | "control_library" | "control_knowledge" | null,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of understanding",
  "clarifying_question": "Question for user (only when action is 'clarify')",
  "parameters": {
    "mode": "all" | "category" | "risk_id" | "risk_description",
    "risk_category": "string (if mode=category)",
    "risk_id": "string (if mode=risk_id)",
    "risk_description": "string (if mode=risk_description)"
  }
}
```

## Generation Mode Detection
When routing to generate_control, analyze the user input to determine generation parameters:

- **mode: "all"** - Generate controls for all user's risks
  - "Generate controls for all my risks"
  - "Create security controls for my organization"
  
- **mode: "category"** - Generate controls for specific risk category
  - "Generate controls for financial risks" → risk_category: "Financial"
  - "Create controls for cyber security risks" → risk_category: "Cyber Security"
  - "I need controls for operational risks" → risk_category: "Operational"
  
- **mode: "risk_id"** - Generate controls for specific risk ID
  - "Generate controls for risk R-001" → risk_id: "R-001"
  - "Create controls for RISK-123" → risk_id: "RISK-123"
  
- **mode: "risk_description"** - Generate controls for described risk
  - "Generate controls for data breach risk" → risk_description: "data breach risk"
  - "Create controls for SQL injection vulnerability" → risk_description: "SQL injection vulnerability"

## Common Risk Categories
- Financial, Operational, Strategic, Compliance, Technology, Cyber Security, Data Privacy, 
- Human Resources, Environmental, Legal, Reputational, Supply Chain

## Classification Examples

### Generation Intent (route to generate_control):
- "Generate controls for financial risks" 
  ```json
  {
    "action": "route",
    "sub_domain": "generate_control",
    "confidence": 0.9,
    "reasoning": "Clear intent to generate controls for specific category",
    "parameters": {"mode": "category", "risk_category": "Financial"}
  }
  ```

- "Create controls for risk R-001"
  ```json
  {
    "action": "route", 
    "sub_domain": "generate_control",
    "confidence": 0.95,
    "reasoning": "Specific risk ID mentioned",
    "parameters": {"mode": "risk_id", "risk_id": "R-001"}
  }
  ```

- "I need controls for ransomware attacks"
  ```json
  {
    "action": "route",
    "sub_domain": "generate_control", 
    "confidence": 0.85,
    "reasoning": "Specific risk described",
    "parameters": {"mode": "risk_description", "risk_description": "ransomware attacks"}
  }
  ```

### Library Intent (route to control_library):
- "Show me my existing controls"
- "List controls I've saved" 
- "Find controls for risk R-001"
- "What controls do I have implemented?"
- "Search my controls for encryption"
- "Find controls related to A.9.2" (ISO 27001 Annex A reference)
- "Show me controls for A.5.23"
- "List my controls mapped to A.12.1"
- "Search controls by annex reference"

```json
{
  "action": "route",
  "sub_domain": "control_library", 
  "confidence": 0.9,
  "reasoning": "User wants to search their saved controls for Annex A.9.2 references",
  "parameters": {"annex_reference": "A.9.2"}
}
```

### Knowledge Intent (route to control_knowledge):
- "What are access controls?"
- "Explain preventive vs detective controls"
- "Tell me about NIST control framework"
- "How do technical controls work?"
- "What's the difference between administrative and physical controls?"
- "How can I implement this control in my org?"
- "How to implement regular health and safety audits?"
- "What are the steps to deploy this control?"
- "How do I operationalize control C-002?"
- "Implementation guidance for infection control measures"

```json
{
  "action": "route",
  "sub_domain": "control_knowledge",
  "confidence": 0.9,
  "reasoning": "User asking for implementation guidance for a specific control",
  "parameters": {"query_type": "implementation", "control_context": "health and safety audits"}
}
```

### Clarification Examples:
User: "I need help with controls"
```json
{
  "action": "clarify",
  "sub_domain": null,
  "confidence": 0.3,
  "reasoning": "Ambiguous - could be generation, library access, or educational need",
  "clarifying_question": "I'm here to help with controls. Are you looking to: create new controls for specific risks, review controls you've already saved, or learn about different types of security controls?"
}
```

User: "Show me controls for A.5.23"
```json
{
  "action": "clarify", 
  "sub_domain": null,
  "confidence": 0.6,
  "reasoning": "Could be asking for user's saved controls mapped to A.5.23 or general information about A.5.23 controls",
  "clarifying_question": "For ISO 27001 A.5.23 controls - are you looking for controls you've created and saved that map to this annex, or do you want to learn about what A.5.23 covers in general?"
}
```

## Key Semantic Patterns
- **Personal Ownership Indicators**: "my", "our", "I have", "we created" → control_library
- **Creation Language**: "generate", "create", "build", "develop", "design" → generate_control  
- **Educational Language**: "what is", "explain", "how does", "tell me about" → control_knowledge
- **Implementation Language**: "how can I implement", "how to deploy", "implementation steps", "operationalize", "how do I" → control_knowledge
- **Search/Filter Language**: "show", "list", "find", "search" + context clues → library vs knowledge
- **Annex A References**: "A.9.2", "A.5.23", "annex A" + search intent → control_library (NOT generate_control)
- **Risk Categories**: "Financial", "Operational", "Cyber Security" + generate intent → generate_control
- **Context References**: "this control", "that control", "the control we discussed" → use conversation context

## Context Considerations
- Use conversation history to understand previous context
- Consider user's organizational role and needs
- Reference prior work: "Based on the risks we identified earlier..."
- Build understanding progressively through conversation
"""

    try:
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        
        # Parse JSON response
        content = response_content.strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
            else:
                # Fallback
                result = {
                    "action": "clarify",
                    "sub_domain": None,
                    "confidence": 0.0,
                    "reasoning": "Could not parse intent",
                    "clarifying_question": "I'd like to help you with security controls. Could you tell me more about what you're trying to accomplish - are you looking to create new controls, review existing ones, or learn about control concepts?"
                }
        
        action = result.get("action", "clarify")
        sub_domain = result.get("sub_domain")
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")
        clarifying_question = result.get("clarifying_question", "")
        parameters = result.get("parameters", {})
        
        print(f"DEBUG: Control node - Action: {action}, Sub-domain: {sub_domain}, Confidence: {confidence}")
        print(f"DEBUG: Control node - Reasoning: {reasoning}")
        print(f"DEBUG: Control node - Parameters: {parameters}")
        
        # Set control-related flags
        state["is_control_related"] = True
        
        # Handle routing decision
        if action == "route" and sub_domain and confidence >= 0.8:
            if sub_domain == "generate_control":
                state["control_target"] = "generate_control_node"
                state["control_generation_requested"] = True
                
                # Extract and set control parameters
                control_params = {}
                if parameters:
                    control_params["mode"] = parameters.get("mode", "all")
                    if "risk_category" in parameters:
                        control_params["risk_category"] = parameters["risk_category"]
                    if "risk_id" in parameters:
                        control_params["risk_id"] = parameters["risk_id"]
                    if "risk_description" in parameters:
                        control_params["risk_description"] = parameters["risk_description"]
                else:
                    # Fallback parameter extraction from user input
                    user_lower = user_input.lower()
                    if "risk" in user_lower and any(cat.lower() in user_lower for cat in ["financial", "operational", "strategic", "compliance", "technology", "cyber", "data", "hr", "environmental", "legal", "reputational", "supply"]):
                        control_params["mode"] = "category"
                        # Extract category name
                        for cat in ["financial", "operational", "strategic", "compliance", "technology", "cyber security", "data privacy", "human resources", "environmental", "legal", "reputational", "supply chain"]:
                            if cat.lower() in user_lower:
                                control_params["risk_category"] = cat.title()
                                break
                    elif "risk" in user_lower and ("r-" in user_lower or "risk-" in user_lower):
                        control_params["mode"] = "risk_id"
                        # Try to extract risk ID
                        import re
                        risk_id_match = re.search(r'(r-\d+|risk-\d+)', user_lower)
                        if risk_id_match:
                            control_params["risk_id"] = risk_id_match.group(1).upper()
                    else:
                        control_params["mode"] = "all"
                
                state["control_parameters"] = control_params
                
                # Also set risk_description in state if mode is risk_description
                if control_params.get("mode") == "risk_description":
                    state["risk_description"] = control_params.get("risk_description", "")
                
                print(f"DEBUG: Routing to generate_control_node with parameters: {control_params}")
                return state
            elif sub_domain == "control_library":
                state["control_target"] = "control_library_node"
                
                # Extract and set search parameters for control library
                control_params = {}
                if parameters:
                    # Don't pass mode for control_library searches - let the library node handle the query directly
                    control_params = {k: v for k, v in parameters.items() if k not in ["mode", "risk_category"]}
                    if "annex_reference" in parameters:
                        control_params["annex_reference"] = parameters["annex_reference"]
                else:
                    # Check if user is asking about specific Annex A references
                    user_lower = user_input.lower()
                    import re
                    annex_match = re.search(r'a\.?\s*(\d+)\.?\s*(\d+)?', user_lower)
                    if annex_match:
                        annex_ref = f"A.{annex_match.group(1)}"
                        if annex_match.group(2):
                            annex_ref += f".{annex_match.group(2)}"
                        control_params["annex_reference"] = annex_ref
                
                state["control_parameters"] = control_params
                print(f"DEBUG: Routing to control_library_node with parameters: {control_params}")
                return state
            elif sub_domain == "control_knowledge":
                state["control_target"] = "control_knowledge_node"
                
                # Extract and set knowledge parameters
                control_params = {}
                if parameters:
                    control_params = {k: v for k, v in parameters.items()}
                else:
                    # Check for implementation questions
                    user_lower = user_input.lower()
                    if any(word in user_lower for word in ["implement", "deploy", "operationalize", "how to", "how can i"]):
                        control_params["query_type"] = "implementation"
                        # Try to extract control context from conversation
                        if "this control" in user_lower or "the control" in user_lower:
                            control_params["has_context"] = True
                
                state["control_parameters"] = control_params
                print(f"DEBUG: Routing to control_knowledge_node with parameters: {control_params}")
                return state
        
        # Ask clarifying question
        if not clarifying_question:
            clarifying_question = "I'm here to help with security controls. Are you looking to create new controls, review existing ones you've saved, or learn about control frameworks and concepts?"
        
        # Update conversation history and return response
        updated_history = conversation_history + [
            {"user": user_input, "assistant": clarifying_question}
        ]
        
        return {
            **state,
            "output": clarifying_question,
            "conversation_history": updated_history,
            "control_target": "clarify"  # Indicate we're in clarification mode
        }
        
    except Exception as e:
        print(f"Error in control_node: {str(e)}")
        error_response = "I want to help you with security controls, but I need to understand your specific need. Are you looking to create new controls, manage existing ones, or learn about control concepts?"
        
        updated_history = conversation_history + [
            {"user": user_input, "assistant": error_response}
        ]
        
        return {
            **state,
            "output": error_response, 
            "conversation_history": updated_history,
            "is_control_related": True,
            "control_target": "clarify"
        }


def route_control_three_way(state: LLMState) -> str:
    """
    Fixed three-way routing function that properly handles all control sub-domains
    """
    control_target = state.get("control_target", "control_library_node")
    
    print(f"DEBUG: Control three-way routing - target: {control_target}")
    
    # Handle clarification state - stay in control node for another round
    if control_target == "clarify":
        return "control_node"
    
    # Route to appropriate sub-domain
    if control_target == "generate_control_node":
        return "generate_control_node"
    elif control_target == "control_knowledge_node":
        return "control_knowledge_node"
    elif control_target == "control_library_node":
        return "control_library_node"
    
    # Default fallback
    print(f"DEBUG: Unknown control target '{control_target}', defaulting to control_library_node")
    return "control_library_node"
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="generate_control_node")
def control_generate_node(state: LLMState) -> LLMState:
    """
    Generate controls using direct LLM calls with conversation history
    """
    print("Control Generate Node Activated")
    
    conversation_history = state.get("conversation_history", [])
    user_data = state.get("user_data", {})
    user_id = user_data.get("username") or user_data.get("user_id") or ""
    params = state.get("control_parameters", {}) or {}
    mode = params.get("mode", "all")

    all_controls = []

    try:
        risks = []
        from vector_index import VectorIndexService

        if mode == "risk_id":
            rid = params.get("risk_id", "")
            if rid:
                r = ControlsDatabaseService.get_risk_by_id(rid, user_id)
                if r:
                    risks = [r]
        elif mode == "risk_description":
            desc = (state.get("risk_description") or "").strip()
            if desc:
                sr = VectorIndexService.search(user_id=user_id, query=desc, top_k=1, filters={})
                hits = sr.get("results", [])
                if hits:
                    h = hits[0]
                    risk_text = h.get("risk_text", "")
                    description = risk_text.split("Risk: ")[-1].split(". Likelihood:")[0] if "Risk: " in risk_text else risk_text
                    risks = [{
                        "id": h.get("risk_id"),
                        "description": description,
                        "category": h.get("category"),
                        "likelihood": "Medium",
                        "impact": "Medium",
                        "treatment_strategy": "",
                        "user_id": user_id
                    }]
                else:
                    risks = [{
                        "id": "",
                        "description": desc,
                        "category": "Technology",
                        "likelihood": "Medium",
                        "impact": "Medium",
                        "treatment_strategy": "",
                        "user_id": user_id
                    }]
        elif mode == "category":
            target_cat = (params.get("risk_category") or "").strip()
            # Try semantic search first
            sr = VectorIndexService.search(
                user_id=user_id,
                query=(target_cat + " risks mitigation") if target_cat else state.get("input", "relevant risks"),
                top_k=50,
                filters={},
            )
            hits = sr.get("results", [])
            for h in hits:
                hcat = str(h.get("category", ""))
                if target_cat and hcat.lower() != target_cat.lower():
                    continue
                risk_text = h.get("risk_text", "")
                description = risk_text.split("Risk: ")[-1].split(". Likelihood:")[0] if "Risk: " in risk_text else risk_text
                risks.append({
                    "id": h.get("risk_id"),
                    "description": description,
                    "category": hcat,
                    "likelihood": "Medium",
                    "impact": "Medium",
                    "treatment_strategy": "",
                    "user_id": user_id,
                })
            if not risks:
                all_risks = ControlsDatabaseService.get_user_risks(user_id)
                risks = [r for r in all_risks if str(r.get("category", "")).lower() == target_cat.lower()] if target_cat else all_risks
        else:
            sr = VectorIndexService.search(user_id=user_id, query="all risks security controls mitigation", top_k=50, filters={})
            hits = sr.get("results", [])
            for h in hits:
                risk_text = h.get("risk_text", "")
                description = risk_text.split("Risk: ")[-1].split(". Likelihood:")[0] if "Risk: " in risk_text else risk_text
                risks.append({
                    "id": h.get("risk_id"),
                    "description": description,
                    "category": h.get("category"),
                    "likelihood": "Medium",
                    "impact": "Medium",
                    "treatment_strategy": "",
                    "user_id": user_id
                })
            if not risks:
                risks = ControlsDatabaseService.get_user_risks(user_id)

        print(f"DEBUG: control_generate_node - generating for {len(risks)} risk(s)")

        for r in risks:
            controls = generate_controls_for_risk(r, user_data, conversation_history)
            link_risk = not (mode == "risk_description" and r.get("id", "") == "")
            for c in controls:
                if link_risk and r.get("id"):
                    # Ensure linked_risk_ids is a list and add the risk ID
                    if "linked_risk_ids" not in c:
                        c["linked_risk_ids"] = []
                    if r.get("id") not in c["linked_risk_ids"]:
                        c["linked_risk_ids"].append(r.get("id"))
                c["user_id"] = user_id
                c["id"] = str(uuid.uuid4())
            if controls:
                # Do not save here; return to frontend for selection
                all_controls.extend(controls)

        # Return generated controls for popup; frontend will save selected ones
        rc = state.get("risk_context", {}) or {}
        rc["generated_controls"] = all_controls
        state["risk_context"] = rc
        state["generated_controls"] = all_controls
        state["output"] = (f"Generated {len(all_controls)} controls. "
                            f"Please select controls to save via the control API.")
        return state
    except Exception as e:
        state["output"] = f"Error generating controls: {str(e)}"
        return state

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_library_node")
def control_library_node(state: LLMState) -> LLMState:
    """Conversational control library assistant for searching and managing user's controls"""
    print("Control Library Node Activated")
    
    user_input = state.get("input", "")
    user_data = state.get("user_data", {})
    conversation_history = state.get("conversation_history", [])
    control_parameters = state.get("control_parameters", {})
    user_id = user_data.get("username") or user_data.get("user_id") or ""
    model = get_llm()
    
    # Check if we have specific Annex A reference parameters
    search_query = user_input
    if control_parameters.get("annex_reference"):
        annex_ref = control_parameters["annex_reference"]
        search_query = f"controls related to ISO 27001 Annex {annex_ref} {user_input}"
        print(f"DEBUG: Enhanced search query for Annex reference: {search_query}")
    search_intent_prompt = f"""You are the Control Library assistant.

- If the user is asking to **find/search/list/filter/sort** controls or anything that
  requires looking up their previously **finalized controls**, you MUST call the tool
  `semantic_control_search` with:
    - query: "{search_query}"
    - user_id: "{user_id}"
    - top_k: pick 5-10 based on query breadth (default 5)

- If the query is related to both controls and risks, you must call both tools:
  - `semantic_control_search` for controls. You will find the risk mongodb Ids in the control metadata.
  - `semantic_risk_search` for risks

- After you get tool results, respond with:
  1) a short, clear natural-language summary (what you found and why it matches)
- If the user only says things like “open my risk register” (no search),
  DO NOT call the tool. Just acknowledge that the register is open and instruct
  how to ask search queries naturally (e.g., “find cyber risks about ransomware”).
"""

    try:
        messages = [SystemMessage(content=search_intent_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for ex in recent_history:
            if ex.get("user"):
                messages.append(HumanMessage(content=ex["user"]))
            if ex.get("assistant"):
                messages.append(AIMessage(content=ex["assistant"]))

        messages.append(HumanMessage(content=user_input))
        agent = create_react_agent(
            model=model,
            tools=[semantic_control_search, semantic_risk_search],
        )
        result = agent.invoke({"messages": messages})
        final_text = ""
        try:
            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                final_text = getattr(last, "content", "") or ""
                if isinstance(final_text, list):
                    final_text = " ".join(
                        [getattr(p, "content", p) for p in final_text if p]
                    )
        except Exception:
            pass

        if not final_text:
            final_text = (
                "I've opened your control library. You can ask me to search it, e.g., "
                "“find controls related to cybersecurity” or “show data privacy controls.”"
            )
        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]

        return {
            "output": final_text,
            "conversation_history": updated_history,
            "user_data": user_data
        }

    except Exception as e:
        print(f"Intent parsing failed: {e}")
        error_response = (
            "I understand you want to access your control library. I’ve opened it. "
            "You can ask me to search it (e.g., “find me cybersecurity controls”)."
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
            "risk_register_requested": False
        }

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_knowledge_node")
def control_knowledge_node(state: LLMState) -> LLMState:
    print("Control Knowledge Node Activated")
    try:
        user_input = state.get("input", "")
        conversation_history = state.get("conversation_history", [])
        control_parameters = state.get("control_parameters", {})
        
        # Extract context from recent conversation about controls
        recent_control_context = ""
        for msg in conversation_history[-3:]:  # Look at last 3 exchanges
            if msg.get("assistant") and any(keyword in msg["assistant"].lower() for keyword in ["control id:", "control title:", "c-", "annex a"]):
                recent_control_context += f"Previous context: {msg['assistant']}\n"
        
        from knowledge_base import ISO_27001_KNOWLEDGE
        system_prompt = f"""
You are an ISO 27001:2022 controls implementation expert. Your role is to provide practical, actionable guidance for implementing security controls.

RECENT CONVERSATION CONTEXT:
{recent_control_context}

When a user asks about implementation ("how can I implement", "how to deploy", "implementation steps"), provide:
1. **Step-by-step implementation guidance**
2. **Organizational considerations**
3. **Resource requirements**
4. **Success metrics/KPIs**
5. **Common challenges and solutions**
6. **Best practices**

For general control questions, use the provided dataset to answer about Annex A domains and controls. Be concise and map queries to control IDs where possible.

DATASET:
{ISO_27001_KNOWLEDGE}

If the user is asking about implementing a specific control mentioned in the recent conversation, provide detailed implementation guidance tailored to that control.
"""
        
        resp = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        updated_history = conversation_history + [{"user": user_input, "assistant": resp}]
        return {**state, "output": resp, "conversation_history": updated_history}
        
    except Exception as e:
        error_msg = f"I'd be happy to help with control implementation guidance, but I encountered an error: {str(e)}"
        return {**state, "output": error_msg}

def generate_controls_for_risk(risk_data: dict, user_context: dict, conversation_history: list) -> list:
    """Generate controls for a single risk using direct LLM call"""
    print(f"DEBUG: Entering generate_controls_for_risk for risk: {risk_data.get('description', 'No description')[:50]}...")
    try:
        # Create comprehensive context for control generation
        risk_context = f"""
Risk Details:
- ID: {risk_data.get('id', 'N/A')}
- Description: {risk_data.get('description', '')}
- Category: {risk_data.get('category', '')}
- Impact: {risk_data.get('impact', '')}
- Likelihood: {risk_data.get('likelihood', '')}
- Treatment Strategy: {risk_data.get('treatment_strategy', '')}
- Department: {risk_data.get('department', '')}
- Risk Owner: {risk_data.get('risk_owner', '')}

Organization Context:
- Organization: {user_context.get('organization_name', '')}
- Domain: {user_context.get('domain', '')}
- Location: {user_context.get('location', '')}
"""
        
        # Debug: Check ISO knowledge
        iso_knowledge = ISO_27001_KNOWLEDGE.get("ISO27001_2022", {}).get("Annex_A")
        print(f"DEBUG: ISO Knowledge available: {bool(iso_knowledge)}")
        if iso_knowledge:
            print(f"DEBUG: ISO Knowledge type: {type(iso_knowledge)}")
            if isinstance(iso_knowledge, dict):
                print(f"DEBUG: ISO Knowledge keys: {list(iso_knowledge.keys())[:5]}")
        
        system_prompt = f"""
You are an ISO 27001:2022 Controls Specialist. Based on the risk provided, generate 3-5 specific, actionable ISO 27001:2022 Annex A controls in the comprehensive format.

Knowledge for the ISO 27001:2022 Annex A references:
SOURCE OF TRUTH (read-only)
{ISO_27001_KNOWLEDGE}
# The above JSON is the canonical dataset. Do not invent entries, numbers, or text that are not present here.

Risk Context:
{risk_context}

Your task is to analyze this risk and generate relevant controls that would effectively mitigate this specific risk.

For each control, provide a comprehensive structure with:
1. control_id: Unique identifier (format: C-[NUMBER], e.g., "C-001", "C-002")
2. control_title: Clear, specific control title
3. control_description: Detailed description of what this control addresses for this risk
4. objective: Business objective and purpose of the control
5. annexA_map: Array of relevant ISO 27001:2022 Annex A mappings with id and title
6. linked_risk_ids: Array containing the risk ID this control addresses
7. owner_role: Suggested role responsible for this control (e.g., "CISO", "IT Manager", "Security Officer")
8. process_steps: Array of 3-5 specific implementation steps
9. evidence_samples: Array of 3-5 examples of evidence/documentation for this control
10. metrics: Array of 2-4 measurable KPIs or metrics to track control effectiveness
11. frequency: How often the control is executed/reviewed (e.g., "Quarterly", "Monthly", "Annually")
12. policy_ref: Reference to related organizational policy
13. status: Set to "Planned" for new controls
14. rationale: Why this control is necessary for mitigating the specific risk
15. assumptions: Any assumptions made (can be empty string if none)

REQUIREMENTS:
- Controls must be specifically relevant to the risk described
- Use appropriate ISO 27001:2022 Annex A references from the knowledge base
- Make controls actionable and specific to the organization context
- Ensure process_steps are concrete and implementable
- Evidence_samples should be realistic audit artifacts
- Metrics should be measurable and relevant to the control objective
- Consider the department and risk owner in the owner_role assignment

Return ONLY a valid JSON array of controls in this format:
[
  {{
    "control_id": "C-001",
    "control_title": "...",
    "control_description": "...",
    "objective": "...",
    "annexA_map": [
      {{"id": "A.X.Y", "title": "..."}}
    ],
    "linked_risk_ids": ["{risk_data.get('id', 'RISK-001')}"],
    "owner_role": "...",
    "process_steps": [
      "Step 1...",
      "Step 2..."
    ],
    "evidence_samples": [
      "Document 1...",
      "Report 2..."
    ],
    "metrics": [
      "Metric 1...",
      "Metric 2..."
    ],
    "frequency": "...",
    "policy_ref": "...",
    "status": "Planned",
    "rationale": "...",
    "assumptions": ""
  }}
]

Do not include any explanatory text, only the JSON array.
"""

        user_input = f"Generate ISO 27001 controls for the risk: {risk_data.get('description', '')}"
        print(f"DEBUG: Making LLM call with user_input: {user_input[:100]}...")
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        print(f"DEBUG: LLM response length: {len(response_content)}")
        print(f"DEBUG: LLM response preview: {response_content[:200]}...")
        
        # Parse JSON response
        content = response_content.strip()
        if content.startswith("```") and content.endswith("```"):
            content = content.strip('`').strip()
            if content.startswith('json'):
                content = content[4:].strip()
        
        # Extract JSON array
        start = content.find('[')
        end = content.rfind(']')
        print(f"DEBUG: JSON array bounds: start={start}, end={end}")
        if start != -1 and end != -1 and end > start:
            controls_json = content[start:end+1]
            print(f"DEBUG: Extracted JSON: {controls_json[:200]}...")
            controls = json.loads(controls_json)
            print(f"DEBUG: Parsed {len(controls) if isinstance(controls, list) else 0} controls from JSON")
            return controls if isinstance(controls, list) else []
        
        print("DEBUG: No valid JSON array found in response")
        return []
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error in control generation: {e}")
        return []
    except Exception as e:
        print(f"Error generating controls for risk: {e}")
        return []

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="risk_node")
def risk_node(state: LLMState):
    """Conversational risk management assistant with semantic intent understanding"""
    print("Risk Node Activated")
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    user_data = state.get("user_data", {})
    
    # Industry-standard conversational prompt
    system_prompt = """# Risk Management Assistant - Intent Classification

## Role  
You are a conversational risk management specialist. Analyze user intent and either route to appropriate risk sub-domains or ask clarifying questions to better understand their needs.

## Available Risk Sub-Domains
1. **risk_generation**: Creating/generating new organizational risks
2. **risk_register**: Viewing, searching, and managing existing finalized risks  
3. **risk_profiling**: Managing risk profiles, preferences, scales, and frameworks
4. **matrix_recommendation**: Creating or recommending risk assessment matrices
5. **general_guidance**: Providing risk management advice and education

## Task
Understand what the user wants to accomplish with risk management and determine the best way to help them.

## Decision Framework
1. **Semantic Intent Analysis**: What is the user's underlying goal?
2. **Context Integration**: Consider conversation history and organizational context
3. **Confidence Assessment**: Rate understanding confidence (0.0-1.0)
4. **Action Decision**: Route (≥0.8 confidence) or clarify (<0.8 confidence)

## Output Format
```json
{
  "action": "route" | "clarify",
  "sub_domain": "risk_generation" | "risk_register" | "risk_profiling" | "matrix_recommendation" | "general_guidance" | null,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of understanding",
  "extracted_params": {
    "organization_type": "hospital|bank|startup|...",
    "location": "city, country", 
    "domain": "healthcare|financial|technology|...",
    "risk_count": 25,
    "matrix_size": "3x3|4x4|5x5",
    "category_focus": "operational|financial|strategic|..."
  },
  "clarifying_question": "Question for user (only when action is 'clarify')"
}
```

## Intent Classification Examples

### Risk Generation (Create New Risks):
- "Generate 25 cyber risks for our fintech startup"
- "Create operational risks for a hospital in Mumbai" 
- "I need privacy risks for our organization"
- "Help me identify financial risks"

### Risk Register (Manage Existing Risks):
- "Show me all high-impact risks"
- "Find cybersecurity risks in my register"
- "List risks owned by John Smith"
- "Search for data breach risks"
- "Open my risk register"

### Risk Profiling (Preferences & Configuration):
- "Update my risk appetite settings"
- "Change likelihood scale to 1-7"
- "Set default matrix to 4x4"
- "Modify risk profile preferences"
- "Configure risk assessment framework"

### Matrix Recommendation (Risk Assessment Framework):
- "Recommend a risk matrix for my organization"
- "Suggest a 4x4 matrix for healthcare"
- "What matrix size should I use?"
- "Create risk assessment heatmap"
- "Show me matrix options"

### General Guidance (Education & Advice):
- "How do I assess risks?"
- "What's a good risk treatment strategy?"
- "Explain risk appetite vs tolerance"
- "Best practices for risk management"

### Clarification Examples:
User: "Help me with risks"
```json
{
  "action": "clarify",
  "sub_domain": null, 
  "confidence": 0.3,
  "reasoning": "Very broad request - could be generation, viewing existing, or general guidance",
  "clarifying_question": "I'm here to help with risk management. Are you looking to: identify new risks for your organization, review and manage existing risks you've already documented, or get guidance on risk assessment approaches?"
}
```

User: "I need a matrix"
```json
{
  "action": "clarify",
  "sub_domain": null,
  "confidence": 0.5, 
  "reasoning": "Likely wants matrix recommendation but missing context about organization and requirements",
  "clarifying_question": "I'd be happy to recommend a risk assessment matrix. To give you the most suitable recommendation, could you tell me about your organization type and industry? For example, are you working with a startup, established company, healthcare organization, financial services, etc.?"
}
```

## Parameter Extraction Guidelines
When confident about routing, extract relevant parameters from user input:
- **Organization details**: Type, industry, size indicators
- **Location**: Geographic context for regulatory considerations  
- **Risk focus**: Specific categories or domains mentioned
- **Quantities**: Number of risks, matrix dimensions
- **Scope**: Department, project, or organizational level

## Context Integration
- Reference conversation history: "Based on the organization details you mentioned earlier..."
- Build on established context: "For the hospital in Mumbai we discussed..."
- Connect related topics: "Now that we have your risk matrix, would you like to..."

## Conversational Guidelines
- Ask ONE focused question when clarifying
- Offer 2-3 concrete options to help users choose
- Use conversational, professional tone
- Reference user's organizational context when known
- Build understanding progressively through multiple exchanges if needed
"""

    try:
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        
        # Parse JSON response
        content = response_content.strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
            else:
                # Fallback to clarification
                result = {
                    "action": "clarify",
                    "sub_domain": None,
                    "confidence": 0.0,
                    "reasoning": "Could not parse intent",
                    "clarifying_question": "I want to make sure I provide the most helpful risk management assistance. Could you tell me more about what specific aspect you'd like help with - whether it's identifying new risks, managing existing ones, or configuring your risk assessment approach?"
                }
        
        action = result.get("action", "clarify")
        sub_domain = result.get("sub_domain")
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")
        extracted_params = result.get("extracted_params", {})
        clarifying_question = result.get("clarifying_question", "")
        
        print(f"DEBUG: Risk node - Action: {action}, Sub-domain: {sub_domain}, Confidence: {confidence}")
        print(f"DEBUG: Risk node - Reasoning: {reasoning}")
        print(f"DEBUG: Risk node - Extracted params: {extracted_params}")
        
        # Handle routing decision
        if action == "route" and sub_domain and confidence >= 0.8:
            # Store extracted parameters for the target node
            if extracted_params:
                risk_context.update(extracted_params)
            
            # Route to appropriate sub-domain
            if sub_domain == "risk_generation":
                return {
                    "input": state["input"],
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
            elif sub_domain == "risk_register":
                return {
                    "input": state["input"],
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
            elif sub_domain == "risk_profiling":
                return {
                    "input": state["input"],
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
            elif sub_domain == "matrix_recommendation":
                # Extract matrix size if provided
                matrix_size = extracted_params.get("matrix_size", "5x5")
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
                    "matrix_recommendation_requested": True,
                    "matrix_size": matrix_size
                }
            elif sub_domain == "general_guidance":
                # Handle general guidance directly in this node
                guidance_response = provide_risk_guidance(user_input, conversation_history, user_data)
                updated_history = conversation_history + [
                    {"user": user_input, "assistant": guidance_response}
                ]
                return {
                    "input": state["input"],
                    "output": guidance_response,
                    "conversation_history": updated_history,
                    "risk_context": risk_context,
                    "user_data": user_data,
                    "risk_generation_requested": False,
                    "preference_update_requested": False,
                    "risk_register_requested": False,
                    "risk_profile_requested": False,
                    "matrix_recommendation_requested": False
                }
        
        # Ask clarifying question
        if not clarifying_question:
            clarifying_question = "I'm here to help with risk management. Could you tell me more about what you're looking to accomplish - whether it's identifying new risks, managing existing risks, setting up assessment frameworks, or getting guidance on risk management approaches?"
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": clarifying_question}
        ]
        
        return {
            "input": state["input"],
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
        print(f"Error in risk_node: {str(e)}")
        error_response = "I want to help you with risk management. Could you tell me what specific aspect you'd like assistance with - whether it's risk assessment, risk monitoring, or risk treatment planning?"
        
        updated_history = conversation_history + [
            {"user": user_input, "assistant": error_response}
        ]
        
        return {
            "input": state["input"],
            "output": error_response,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False
        }


def provide_risk_guidance(user_input: str, conversation_history: list, user_data: dict) -> str:
    """Provide general risk management guidance and education"""
    
    guidance_prompt = """# Risk Management Guidance Assistant

## Role
You are a helpful risk management consultant providing practical guidance and education.

## Task  
Provide clear, actionable guidance on risk management topics. Use conversational language and practical examples.

## Guidelines
- Keep responses focused and actionable
- Use industry best practices
- Reference relevant frameworks (ISO 31000, COSO, etc.) when appropriate
- Provide concrete examples
- Consider the user's organizational context when known
- Offer next steps or follow-up actions

## Response Style
- Professional but conversational
- Structured with clear headings when covering multiple points
- Include practical tips and best practices
- Suggest related topics or next steps
- Keep responses comprehensive but not overwhelming (aim for 200-400 words)
"""
    
    try:
        response = make_llm_call_with_history(guidance_prompt, user_input, conversation_history)
        return response
    except Exception as e:
        return "I'd be happy to provide risk management guidance. Could you be more specific about the aspect you'd like help with - such as risk identification, assessment methods, treatment strategies, or monitoring approaches?"
    

# 3. Define the risk generation node
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="risk_generation_node")
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
        import traceback
        traceback.print_exc()
        return {
            "output": f"I apologize, but I encountered an error while generating risks for your organization: {str(e)}. Please try again.",
            "conversation_history": state.get("conversation_history", []),
            "risk_context": state.get("risk_context", {}),
            "risk_generation_requested": False,
            "preference_update_requested": False
        }

# 4. Define the preference update node
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="risk_register_node")
def risk_register_node(state: LLMState):
    """Open the risk register, and when the user asks to find/filter risks,
    perform semantic search via a LangGraph tool call (OpenAI model)."""
    print("Risk Register Node Activated")
    try:
        user_input = state["input"]
        conversation_history = state.get("conversation_history", []) or []
        risk_context = state.get("risk_context", {}) or {}
        user_data = state.get("user_data", {}) or {}
        user_id = user_data.get("username", "")
        model = get_llm()

        system_prompt = f"""
You are the Risk Register assistant.

- If the user is asking to **find/search/list/filter/sort** risks or anything that
  requires looking up their previously **finalized risks**, you MUST call the tool
  `semantic_risk_search` with:
    - query: a concise reformulation of the user's ask
    - user_id: "{user_id}"
    - top_k: pick 5-10 based on query breadth (default 5)

- After you get tool results, respond with:
  1) a short, clear natural-language summary (what you found and why it matches)
- If the user only says things like “open my risk register” (no search),
  DO NOT call the tool. Just acknowledge that the register is open and instruct
  how to ask search queries naturally (e.g., “find cyber risks about ransomware”).
        """.strip()

        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for ex in recent_history:
            if ex.get("user"):
                messages.append(HumanMessage(content=ex["user"]))
            if ex.get("assistant"):
                messages.append(AIMessage(content=ex["assistant"]))

        messages.append(HumanMessage(content=user_input))

        agent = create_react_agent(
            model=model,
            tools=[semantic_risk_search],
        )

        result = agent.invoke({"messages": messages})

        final_text = ""
        try:
            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                final_text = getattr(last, "content", "") or ""
                if isinstance(final_text, list):
                    final_text = " ".join(
                        [getattr(p, "content", p) for p in final_text if p]
                    )
        except Exception:
            pass

        if not final_text:
            # Fallback to a simple open-register message when nothing returned
            final_text = (
                "I’ve opened your risk register. You can ask me to search it, e.g., "
                "“find cyber risks about ransomware” or “show data privacy risks with high impact.”"
            )

        # Update conversation history
        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]

        return {
            "output": final_text,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False
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
            "risk_register_requested": False
        }

# 5. Define the matrix recommendation node
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="matrix_recommendation_node")
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
            from database import RiskProfileDatabaseService
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
        import traceback; traceback.print_exc()
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

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="orchestrator_node")
def orchestrator_node(state: LLMState) -> LLMState:
    """Conversational orchestrator that uses LLM for semantic intent understanding"""
    print("Orchestrator Activated")
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    user_data = state.get("user_data", {})
    
    # Industry-standard prompt with clear role, task, and output format
    system_prompt = """# Risk Management Assistant - Intent Classification

## Role
You are a conversational intent classifier for a Risk Management Assistant that helps organizations with risk assessment, security controls, compliance, and ISO 27001 guidance.

## Task
Analyze the user's query within conversation context and determine the most appropriate action. You can either:
1. Route to a specialized domain when intent is clear and confident
2. Ask clarifying questions when intent is unclear or could have multiple interpretations

## Available Domains
- **risk_domain**: Risk assessment, risk registers, risk matrices, risk profiling, risk generation, risk scoring, risk treatment
- **control_domain**: Security controls, control implementation, control generation, control management, control frameworks
- **knowledge_domain**: ISO 27001 standards, information security concepts, compliance guidance, educational content
- **audit_domain**: Audit processes, audit findings, audit compliance, audit documentation

## Decision Process
1. **Semantic Analysis**: Understand the user's underlying goal and intent
2. **Confidence Assessment**: Rate your confidence in understanding the intent (0.0-1.0)
3. **Action Decision**: 
   - If confidence >= 0.8: Route to appropriate domain
   - If confidence < 0.8: Ask clarifying questions

## Output Format
Return a JSON object with exactly this structure:

```json
{
  "action": "route" | "clarify",
  "domain": "risk_domain" | "control_domain" | "knowledge_domain" | "audit_domain" | null,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of your understanding",
  "clarifying_question": "Question to ask user (only when action is 'clarify')"
}
```

## Clarifying Question Guidelines
When asking clarifying questions:
- Ask ONE specific, focused question
- Reference conversation context when relevant
- Help narrow down the intent without being overwhelming
- Use natural, conversational language
- Offer 2-3 concrete options when helpful

## Example Classifications

### High Confidence Routing Examples:
User: "Show me all cybersecurity risks in my organization"
```json
{
  "action": "route",
  "domain": "risk_domain", 
  "confidence": 0.95,
  "reasoning": "Clear request to view existing risks with specific category filter"
}
```

User: "Generate ISO 27001 controls for data protection"
```json
{
  "action": "route",
  "domain": "control_domain",
  "confidence": 0.90, 
  "reasoning": "Specific request to generate security controls with clear scope"
}
```

User: "What does clause 6.2 of ISO 27001 say?"
```json
{
  "action": "route",
  "domain": "knowledge_domain",
  "confidence": 0.95,
  "reasoning": "Direct question about specific ISO standard clause content"
}
```

### Clarification Examples:
User: "I need help with my matrix"
```json
{
  "action": "clarify",
  "domain": null,
  "confidence": 0.4,
  "reasoning": "Ambiguous request - could be risk matrix creation, viewing existing matrix, or matrix configuration",
  "clarifying_question": "I'd be happy to help with your matrix. Are you looking to: create a new risk assessment matrix, view your existing risk data in matrix format, or modify your current risk matrix settings?"
}
```

User: "What controls do I need?"
```json
{
  "action": "clarify", 
  "domain": null,
  "confidence": 0.5,
  "reasoning": "Could be asking for control generation, control education, or control recommendations",
  "clarifying_question": "To give you the most relevant guidance - are you looking to generate specific controls for identified risks, learn about different types of security controls, or get recommendations for your industry?"
}
```

## Context Considerations
- Use conversation history to inform understanding
- Consider user's organizational context (industry, role, previous topics)
- Reference previous topics naturally: "Earlier you mentioned risks - are you looking to..."
- Build on established context rather than starting fresh each time

## Important Notes
- Never use keyword matching - rely on semantic understanding
- When uncertain, always ask rather than guess
- Keep clarifying questions conversational and helpful
- Consider the user's expertise level in your language choices
"""

    try:
        # Get LLM response for intent classification
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
        
        # Parse the JSON response
        content = response_content.strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        
        # Extract JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: try to find JSON in response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                result = json.loads(content[start:end])
            else:
                # Ultimate fallback - ask for clarification
                result = {
                    "action": "clarify",
                    "domain": None,
                    "confidence": 0.0,
                    "reasoning": "Could not parse intent",
                    "clarifying_question": "I want to make sure I understand what you're looking for. Could you tell me more about what specific task I can help you with regarding risk management, security controls, or compliance?"
                }
        
        action = result.get("action", "clarify")
        domain = result.get("domain")
        clarifying_question = result.get("clarifying_question", "")
        reasoning = result.get("reasoning", "")
        confidence = result.get("confidence", 0.0)
        
        print(f"DEBUG: Orchestrator - Action: {action}, Domain: {domain}, Confidence: {confidence}")
        print(f"DEBUG: Orchestrator - Reasoning: {reasoning}")
        
        # Handle the decision
        if action == "route" and domain and confidence >= 0.8:
            # Route to the specified domain
            if domain == "risk_domain":
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
                    "is_risk_related": True,
                    "is_control_related": False,
                    "is_knowledge_related": False
                }
            elif domain == "control_domain":
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
                    "is_control_related": True,
                    "is_knowledge_related": False
                }
            elif domain == "knowledge_domain":
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
                    "is_control_related": False,
                    "is_knowledge_related": True
                }
            elif domain == "audit_domain":
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
                    "is_risk_related": False,
                    "is_control_related": False,
                    "is_knowledge_related": False
                }
        
        # Default to clarification - ask the clarifying question
        if not clarifying_question:
            clarifying_question = "I want to make sure I provide the most helpful guidance. Could you tell me more about what specific aspect of risk management, security controls, or compliance you'd like help with?"
        
        # Update conversation history with clarifying question
        updated_history = conversation_history + [
            {"user": user_input, "assistant": clarifying_question}
        ]
        
        # Return with clarifying question as output
        return {
            "input": state["input"],
            "output": clarifying_question,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_control_related": False,
            "is_knowledge_related": False
        }
        
    except Exception as e:
        print(f"Error in orchestrator_node: {str(e)}")
        # Fallback to friendly clarification
        clarification_response = "I encountered an issue understanding your request. Could you help me by describing what specific task you'd like assistance with - whether it's related to risk assessment, security controls, or compliance guidance?"
        
        updated_history = conversation_history + [
            {"user": user_input, "assistant": clarification_response}
        ]
        
        return {
            "input": state["input"],
            "output": clarification_response,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_control_related": False,
            "is_knowledge_related": False
        }
    
@traceable(project_name=LANGSMITH_PROJECT_NAME, name="knowledge_node")
def knowledge_node(state: LLMState):
    """Conversational ISO 27001 and information security knowledge assistant"""
    print("Knowledge Node Activated")
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    user_data = state.get("user_data", {})
    
    # Industry-standard conversational prompt for knowledge assistance
    system_prompt = f"""# ISO 27001:2022 Knowledge Assistant

## Role
You are a conversational ISO 27001:2022 expert and information security consultant. Your primary job is to provide accurate, helpful guidance on ISO/IEC 27001:2022 standards, information security management, and compliance topics.

## Knowledge Source
You have access to the complete ISO 27001:2022 dataset below. For any questions about specific clauses, subclauses, or Annex A controls, you MUST answer from this authoritative source:

{ISO_27001_KNOWLEDGE}

## Response Approach
1. **Conversational Style**: Be helpful, professional, and educational
2. **Accuracy First**: Always use the provided dataset for specific ISO references
3. **Context Awareness**: Consider the user's organizational context and conversation history
4. **Practical Focus**: Provide actionable guidance, not just theoretical information
5. **Educational Value**: Help users understand WHY things matter, not just WHAT they are

## Task Guidelines

### For Specific Clause/Control Queries:
When users ask about specific clauses (e.g., "5.2", "Clause 7.5") or Annex A controls (e.g., "A.5.23", "A.8.11"):
- Look up the exact reference in the dataset
- Provide: ID, title, description (if available)
- For top-level clauses: list all subclauses with IDs and titles
- For Annex A domains: list all controls with IDs and titles  
- If description is missing from dataset, provide relevant context based on the title

### For General ISO 27001 Questions:
When users ask broader questions about ISO 27001 (e.g., "What is ISO 27001?", "How does certification work?"):
- Provide concise, practical answers using general ISO knowledge
- When relevant, point to specific clauses or Annex A controls from the dataset
- Include a "See also" section referencing applicable dataset entries

### For Educational/Guidance Requests:
When users need help understanding concepts or implementation:
- Explain concepts clearly with practical examples
- Connect theory to real-world application
- Suggest related clauses or controls from the dataset
- Offer implementation guidance and best practices

## Response Structure
For specific lookups, use this format:
**[Clause/Control ID]: [Title]**
[Description/explanation]

For subclauses or controls under a domain:
- **[ID]**: [Title]
- **[ID]**: [Title]
[etc.]

For general guidance, structure responses with:
- Clear explanation of the concept
- Practical examples or applications  
- Related references from the dataset (when applicable)
- Next steps or recommendations

## Conversational Elements
- Ask follow-up questions when helpful: "Would you like me to explain how this applies to your [industry/organization]?"
- Reference conversation context: "Building on what we discussed about risks..."
- Offer related information: "You might also be interested in..."
- Provide implementation tips: "A practical way to implement this is..."
- Connect to user's context when known

## Error Handling
- If a specific ID isn't found in the dataset: "I couldn't find that exact reference in the ISO 27001:2022 dataset. The closest match would be..."
- For unclear queries: Ask clarifying questions to better understand their need
- Never fabricate clause numbers, titles, or descriptions not in the dataset

## Example Responses

### Specific Clause Query:
User: "What does clause 5.2 say?"
Response: "**5.2: Information security policy**
[Include description from dataset]

This clause requires your organization to establish a comprehensive information security policy that demonstrates management commitment and provides a framework for setting security objectives. 

Would you like me to explain how to develop an effective information security policy, or are you interested in related controls from Annex A that support policy implementation?"

### General Knowledge Query:
User: "What is risk treatment in ISO 27001?"
Response: "Risk treatment in ISO 27001 refers to the process of selecting and implementing measures to modify risk levels. The standard defines four main risk treatment options:

1. **Risk Modification** - Implement controls to reduce likelihood or impact
2. **Risk Retention** - Accept the risk as-is (often for low-level risks)
3. **Risk Avoidance** - Eliminate the risk by avoiding the activity
4. **Risk Sharing** - Transfer risk through insurance, outsourcing, etc.

**See also from the dataset:**
- **Clause 6.1.3**: Risk treatment process requirements
- **Annex A.5**: Organizational controls for risk treatment
- **Clause 8.1**: Operational planning for risk treatment

Would you like me to elaborate on any specific risk treatment approach or explain how to document your risk treatment decisions?"

## Key Principles
- Maintain conversational, helpful tone throughout
- Always verify information against the provided dataset for ISO-specific content
- Provide practical, actionable guidance beyond just definitions  
- Build understanding progressively through the conversation
- Connect information security concepts to business value and outcomes
"""

    try:
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)

        # Add conversational follow-up suggestions based on the response content
        follow_up_prompt = f"""Based on your response about ISO 27001, suggest 1-2 brief, natural follow-up questions or topics that might be helpful to the user. Keep suggestions conversational and relevant to their query.

Your response was: {response_content[:300]}...
User's original question: {user_input}

Provide follow-up suggestions in this format:
**Follow-up suggestions:**
- [Question/topic 1]
- [Question/topic 2] (if applicable)

Keep suggestions brief and natural. Only include if genuinely helpful."""

        # Generate follow-up suggestions
        try:
            follow_up_content = make_llm_call_with_history(follow_up_prompt, "", [])
            if "Follow-up suggestions:" in follow_up_content and len(follow_up_content.strip()) < 200:
                response_content += f"\n\n{follow_up_content.strip()}"
        except:
            # Skip follow-ups if there's any issue generating them
            pass

        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_content}
        ]
        
        return {
            "input": state["input"],
            "output": response_content,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_control_related": False,
            "is_knowledge_related": False
        }
        
    except Exception as e:
        print(f"Error in knowledge_node: {str(e)}")
        
        # Provide helpful fallback response
        error_response = """I'd be happy to help with ISO 27001:2022 guidance and information security questions. 

I can assist with:
- Specific clause explanations (e.g., "What does clause 6.1 cover?")
- Annex A control details (e.g., "Tell me about A.8.24")
- Implementation guidance and best practices
- Information security management concepts
- Compliance and certification questions

What specific aspect of ISO 27001 or information security would you like to explore?"""
        
        updated_history = conversation_history + [
            {"user": user_input, "assistant": error_response}
        ]
        
        return {
            "input": state["input"],
            "output": error_response,
            "conversation_history": updated_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "risk_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False,
            "risk_profile_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_control_related": False,
            "is_knowledge_related": False
        }

# Build the graph with the state schema
builder = StateGraph(LLMState)
builder.add_node("orchestrator", orchestrator_node)
builder.add_node("risk_node", risk_node)
builder.add_node("risk_generation", risk_generation_node)
builder.add_node("risk_register", risk_register_node)
builder.add_node("matrix_recommendation", matrix_recommendation_node)
builder.add_node("knowledge_node", knowledge_node)
builder.add_node("control_node", control_node)
builder.add_node("generate_control_node", control_generate_node)
builder.add_node("control_library_node", control_library_node)
builder.add_node("control_knowledge_node", control_knowledge_node)
builder.set_entry_point("orchestrator")

# Updated orchestrator routing function 
def orchestrator_routing(state: LLMState) -> str:
    """Route based on domain flags set by conversational orchestrator"""
    if state.get("is_audit_related", False):
        return "audit_facilitator"  # Will route to risk_node temporarily until implemented
    elif state.get("is_risk_related", False):
        return "risk_node"
    elif state.get("is_control_related", False):
        return "control_node"
    elif state.get("is_knowledge_related", False):
        return "knowledge_node"
    else:
        # If no flags set, orchestrator is handling conversation directly
        return END

# Updated control routing function (already fixed above)
def route_control_three_way(state: LLMState) -> str:
    """Route to appropriate control sub-domain or continue conversation"""
    control_target = state.get("control_target", "control_library_node")
    
    print(f"DEBUG: Control three-way routing - target: {control_target}")
    
    # Handle clarification state - return to control node for continued conversation
    if control_target == "clarify":
        # Check if we have an output (clarifying question) - if so, end the conversation
        if state.get("output"):
            return END
        else:
            # Continue in control node for another round of clarification
            return "control_node"
    
    # Route to appropriate sub-domain
    if control_target == "generate_control_node":
        return "generate_control_node"
    elif control_target == "control_knowledge_node":
        return "control_knowledge_node"
    elif control_target == "control_library_node":
        return "control_library_node"
    
    # Default fallback
    print(f"DEBUG: Unknown control target '{control_target}', defaulting to control_library_node")
    return "control_library_node"

# Updated risk routing function
def should_generate_risks(state: LLMState) -> str:
    """Route risk sub-domain requests or end if handled in risk_node"""
    
    # Check if risk_node handled the request directly (general guidance)
    if state.get("output"):
        return END
    
    # Route to specific risk sub-domains
    if state.get("risk_generation_requested", False):
        return "risk_generation"
    elif state.get("risk_register_requested", False):
        return "risk_register"
    elif state.get("matrix_recommendation_requested", False):
        return "matrix_recommendation"
    
    # End if no specific routing requested
    return END

# Add orchestrator routing with updated logic
builder.add_conditional_edges("orchestrator", orchestrator_routing, {
    "audit_facilitator": "risk_node",  # Temporary routing until audit_facilitator is implemented
    "knowledge_node": "knowledge_node",
    "control_node": "control_node", 
    "risk_node": "risk_node",
    END: END  # For when orchestrator handles conversation directly
})

# Add control sub-domain routing with all three options
builder.add_conditional_edges("control_node", route_control_three_way, {
    "generate_control_node": "generate_control_node",
    "control_library_node": "control_library_node", 
    "control_knowledge_node": "control_knowledge_node",
    "control_node": "control_node",  # For continued clarification
    END: END  # For when control_node provides direct response
})

# Add risk sub-domain routing
builder.add_conditional_edges("risk_node", should_generate_risks, {
    "risk_generation": "risk_generation",
    "risk_register": "risk_register", 
    "matrix_recommendation": "matrix_recommendation",
    END: END  # For when risk_node provides direct response
})

# Terminal edges for all sub-domain nodes
builder.add_edge("risk_generation", END)
builder.add_edge("risk_register", END)
builder.add_edge("matrix_recommendation", END)
builder.add_edge("knowledge_node", END)
builder.add_edge("generate_control_node", END)
builder.add_edge("control_library_node", END)
builder.add_edge("control_knowledge_node", END)

# Add memory to the graph
memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="run_agent")
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
        "is_risk_related": False,
        "is_control_related": False,
        "is_knowledge_related": False,
        "control_generation_requested": False,
        "control_parameters": {},
        "control_retrieved_context": {},
        "generated_controls": [],
        "selected_controls": [],
        "pending_selection": False,
        "control_session_id": "",
        "control_target": "",
        "control_query": "",
        "control_filters": {},
        "risk_description": ""
    }
    
    # Use thread_id for memory persistence within the session
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(state, config)
    print(f"DEBUG: Final result - output length: {len(result.get('output', ''))}")
    print(f"DEBUG: Final result - risk_context keys: {list(result.get('risk_context', {}).keys())}")
    if 'generated_controls' in result.get('risk_context', {}):
        print(f"DEBUG: Final result has {len(result['risk_context']['generated_controls'])} controls")
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
