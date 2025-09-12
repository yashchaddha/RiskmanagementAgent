import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dependencies import get_llm
from agent import make_llm_call_with_history
from rag_tools import semantic_risk_search, get_risk_profiles, knowledge_base_search, semantic_control_search
from models import LLMState
import json
import uuid
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from database import ControlDatabaseService, RiskDatabaseService
import traceback

# Load environment variables from .env
load_dotenv()

# Set up LangSmith project name
LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")

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
                state["control_generation_requested"] = False  # Library searches don't generate controls
                
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
                state["control_generation_requested"] = False  # Knowledge queries don't generate controls
                
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
            "control_target": "clarify",  # Indicate we're in clarification mode
            "control_generation_requested": False  # Clarifications don't generate controls
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
            "control_target": "clarify",
            "control_generation_requested": False  # Errors don't generate controls
        }

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
        # Build a small ReAct agent for risk lookup to avoid direct tool calls
        model = get_llm()
        def react_search_risks(query: str, uid: str, top_k: int = 5) -> list:
            sys = (
                "You retrieve risks to enable control generation. "
                "Call the `semantic_risk_search` tool with the provided query, user_id, and top_k. "
                "After the tool returns, output ONLY a compact JSON array of risks with fields: "
                "[{'id','description','category','likelihood','impact','treatment_strategy'}]."
            )
            msgs = [SystemMessage(content=sys), HumanMessage(content=f"query={query}\nuser_id={uid}\ntop_k={top_k}")]
            agent = create_react_agent(model=model, tools=[semantic_risk_search])
            result = agent.invoke({"messages": msgs})
            final = result.get("messages", [])[-1]
            content = getattr(final, "content", getattr(final, "text", "")) or ""
            try:
                s = content.find('['); e = content.rfind(']')
                if s != -1 and e != -1 and e > s:
                    return json.loads(content[s:e+1])
            except Exception:
                pass
            return []

        if mode == "risk_id":
            rid = params.get("risk_id", "")
            if rid:
                arr = react_search_risks(query=f"risk ID {rid}", uid=user_id, top_k=1)
                if arr:
                    r0 = arr[0]
                    risks = [{
                        "id": r0.get("id") or r0.get("risk_id", ""),
                        "description": r0.get("description", ""),
                        "category": r0.get("category", ""),
                        "likelihood": r0.get("likelihood", "Medium"),
                        "impact": r0.get("impact", "Medium"),
                        "treatment_strategy": r0.get("treatment_strategy", ""),
                        "user_id": user_id
                    }]
        elif mode == "risk_description":
            # Be robust: pull from state or fallback to parameters
            desc = (state.get("risk_description") or params.get("risk_description") or "").strip()
            if desc:
                arr = react_search_risks(query=desc, uid=user_id, top_k=1)
                if arr:
                    r0 = arr[0]
                    risks = [{
                        "id": r0.get("id") or r0.get("risk_id", ""),
                        "description": r0.get("description", desc),
                        "category": r0.get("category", "Technology"),
                        "likelihood": r0.get("likelihood", "Medium"),
                        "impact": r0.get("impact", "Medium"),
                        "treatment_strategy": r0.get("treatment_strategy", ""),
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
            q = (target_cat + " risks mitigation") if target_cat else state.get("input", "relevant risks")
            arr = react_search_risks(query=q, uid=user_id, top_k=20)
            for h in arr:
                hcat = str(h.get("category", ""))
                if target_cat and hcat.lower() != target_cat.lower():
                    continue
                risks.append({
                    "id": h.get("id") or h.get("risk_id", ""),
                    "description": h.get("description", ""),
                    "category": hcat,
                    "likelihood": h.get("likelihood", "Medium"),
                    "impact": h.get("impact", "Medium"),
                    "treatment_strategy": h.get("treatment_strategy", ""),
                    "user_id": user_id,
                })
            if not risks:
                # Fall back to searching all risks in the category using agent
                fallback_q = f"{target_cat} category risks" if target_cat else "all risks"
                arr2 = react_search_risks(query=fallback_q, uid=user_id, top_k=20)
                for h in arr2:
                    hcat2 = str(h.get("category", ""))
                    if not target_cat or hcat2.lower() == target_cat.lower():
                        risks.append({
                            "id": h.get("id") or h.get("risk_id", ""),
                            "description": h.get("description", ""),
                            "category": hcat2,
                            "likelihood": h.get("likelihood", "Medium"),
                            "impact": h.get("impact", "Medium"),
                            "treatment_strategy": h.get("treatment_strategy", ""),
                            "user_id": user_id,
                        })
        else:
            arr3 = react_search_risks(query="all risks security controls mitigation", uid=user_id, top_k=20)
            for h in arr3:
                risks.append({
                    "id": h.get("id") or h.get("risk_id", ""),
                    "description": h.get("description", ""),
                    "category": h.get("category", ""),
                    "likelihood": h.get("likelihood", "Medium"),
                    "impact": h.get("impact", "Medium"),
                    "treatment_strategy": h.get("treatment_strategy", ""),
                    "user_id": user_id
                })
            if not risks:
                # Fall back to searching all user risks via agent
                arr4 = react_search_risks(query="all user risks", uid=user_id, top_k=20)
                for h in arr4:
                    risks.append({
                        "id": h.get("id") or h.get("risk_id", ""),
                        "description": h.get("description", ""),
                        "category": h.get("category", ""),
                        "likelihood": h.get("likelihood", "Medium"),
                        "impact": h.get("impact", "Medium"),
                        "treatment_strategy": h.get("treatment_strategy", ""),
                        "user_id": user_id
                    })

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
        
        # Flag remains True (set in control_node) to trigger frontend popup
        state["output"] = (f"Generated {len(all_controls)} controls. "
                            f"Please select controls to save via the control API.")
        return state
    except Exception as e:
        # Reset flag on error
        state["control_generation_requested"] = False
        state["output"] = f"Error generating controls: {str(e)}"
        return state

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_library_node")
def control_library_node(state: LLMState) -> LLMState:
    """Conversational control library assistant for searching and managing user's controls"""
    print("Control Library Node Activated")
    
    user_input = state.get("input", "")
    user_data = state.get("user_data", {})
    conversation_history = state.get("conversation_history", [])
    user_id = user_data.get("username") or user_data.get("user_id") or ""
    model = get_llm()
    
    search_intent_prompt = f"""You are the Control Library assistant.

Your job is to help the user search, list, filter, or sort internal controls **from their control library**.

TOOL USE:
- Controls are always mapped to Annexes and not clauses.
- If user asks for controls related/mapped to a any annex (e.g., Annex A.8.30), you MUST call the tool `knowledge_base_search` and then call the `semantic_control_search` tool to get the relevant controls.
- If the user asks to **find/search/list/filter/sort** controls, you MUST call the tool `semantic_control_search`.
- Always include:
  - query: a concise reformulation of the user's ask (defaults to the user's latest message if unspecified)
  - user_id: "{user_id}" (use this value when missing - (not required for knowledge_base_search))
  - top_k: choose 5–10 based on query breadth (default 5)

AFTER THE TOOL RETURNS:
- Read the tool results and produce a clear, helpful natural-language response.
- Summarize what was found and why it matches.
- If results exist, present 3–5 best hits with key fields (e.g., control title, description, owner) in a readable format.
- If no results, suggest alternative terms/broader queries.
- Do NOT dump raw JSON.

IF NO SEARCH IS REQUESTED:
- If the user only says things like "open my control library", do NOT call the tool.
- Briefly confirm it's open and explain how to ask search queries (e.g., “find controls related to cybersecurity”).
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
            tools=[semantic_control_search],
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
            "user_data": user_data,
            "control_generation_requested": False
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
            "control_generation_requested": False,
            "preference_update_requested": False,
            "risk_register_requested": False
        }

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_knowledge_node")
def control_knowledge_node(state: LLMState) -> LLMState:
    print("Control Knowledge Node Activated")
    try:
        user_input = state.get("input", "")
        conversation_history = state.get("conversation_history", [])
        user_data = state.get("user_data", {})
        user_organization = user_data.get("organization_name", "Unknown")
        user_location = user_data.get("location", "Unknown")
        user_domain = user_data.get("domain", "Unknown")
        control_parameters = state.get("control_parameters", {})

        model = get_llm()
        system_prompt = """
You are a **Internal Controls Knowledge Specialist** with deep expertise in internal controls management.  
Your role is to answer user questions about controls, their organization's internal controls, and provide actionable insights.  
Be conversational, helpful, and concise — ask clarifying questions when user input is vague.

---

### USER CONTEXT
Current User ID: "{user_id}"
Organization: {user_organization}
Location: {user_location}
Domain: {user_domain}

---

### AVAILABLE TOOLS

1. **semantic_control_search**  
   Use this when users want:  
   - To find/search specific controls from their control library  
   - To filter controls by annexes, categories, or other attributes  
   - To view specific thematic controls (e.g., cybersecurity, compliance)  

---

### EXPERTISE
You are capable of:
- Explaining internal controls of the organization and categories  
- Analyzing and interpreting control libraries  
- Giving practical recommendations and control implementation strategies  
- Explaining control effectiveness and performance metrics  

---

### RESPONSE STRATEGY

1. **Be Context-Aware:**  
   - Use the organization, location, and domain provided.  
   - If unclear, politely ask for clarification (e.g., "Do you want me to search your control library or explain your specific controls?").  

2. **Provide Actionable Insights:**  
   - After using tools, summarize results in plain language.  
   - Add interpretation, highlight important risks, and suggest next steps where relevant.  

3. **Stay Conversational:**  
   - Keep responses user-friendly, avoid dumping raw JSON unless specifically requested.  
   - You may format results in a clean, structured way (bullet points, tables).  
"""
        messages = [SystemMessage(content=system_prompt)]
        recent = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for ex in recent:
            if ex.get("user"):
                messages.append(HumanMessage(content=ex["user"]))
            if ex.get("assistant"):
                messages.append(AIMessage(content=ex["assistant"]))
        messages.append(HumanMessage(content=user_input))

        agent = create_react_agent(model=model, tools=[knowledge_base_search])
        result = agent.invoke({"messages": messages})
        last = result.get("messages", [])[-1]
        final_text = getattr(last, "content", getattr(last, "text", "")) or "I couldn't retrieve knowledge entries right now. Please try again."
        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
        return {
            **state, 
            "output": final_text, 
            "conversation_history": updated_history,
            "control_generation_requested": False  # Knowledge queries don't generate controls
        }
        
    except Exception as e:
        error_msg = f"I'd be happy to help with control implementation guidance, but I encountered an error: {str(e)}"
        return {
            **state, 
            "output": error_msg,
            "control_generation_requested": False  # Reset flag on error
        }

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
        
        # Search for relevant ISO 27001 knowledge for this risk
        risk_query = f"ISO 27001 controls for {risk_data.get('category', '')} {risk_data.get('description', '')[:100]}"
        iso_search_results = knowledge_base_search.invoke({"query": risk_query, "category": "all", "top_k": 5})
        iso_knowledge_context = ""
        if iso_search_results.get("hits"):
            for hit in iso_search_results["hits"]:
                iso_knowledge_context += f"- {hit.get('text', '')}\n"
        print(f"DEBUG: Retrieved {len(iso_search_results.get('hits', []))} ISO knowledge entries")
        
        system_prompt = f"""
You are an ISO 27001:2022 Controls Specialist. Based on the risk provided, generate 3-5 specific, actionable ISO 27001:2022 Annex A controls in the comprehensive format.

Relevant ISO 27001:2022 Knowledge Base entries for this risk:
{iso_knowledge_context}

# Use the above knowledge entries as guidance for appropriate Annex A mappings and control design.
# Only reference Annex A controls that are relevant to the specific risk being addressed.

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
