import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from models import LLMState
from dependencies import get_llm, make_llm_call_with_history
from agents.risk_agent import risk_node, risk_generation_node, risk_register_node, matrix_recommendation_node, risk_knowledge_node
from agents.control_agent import control_node, control_generate_node, control_library_node, control_knowledge_node
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from rag_tools import knowledge_base_search

# Load environment variables from .env
load_dotenv()

def orchestrator_node(state: LLMState) -> LLMState:
    """Top-level orchestrator with deterministic prefilter and single-token output"""
    print("Orchestrator Activated")
    
    user_input = state["input"]
    conversation_history = state.get("conversation_history", [])
    risk_context = state.get("risk_context", {})
    risk_context["generated_risks"] = False
    risk_context["generated_controls"] = []
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
        control_cues = ["control", "controls", "security control", "iso control", "annex a", "control library", "generate control", "create control", "implementation", "control framework"]
        
        if any(cue in user_text_lower for cue in audit_cues):
            routing_decision = "audit_facilitator"
        elif any(cue in user_text_lower for cue in control_cues):
            routing_decision = "control_node"
        elif any(cue in user_text_lower for cue in risk_cues):
            routing_decision = "risk_node"
        else:
            # Use LLM for edge cases
            system_prompt = """
You are a routing classifier. First understand the context of the user, query and past conversation and accordingly Output EXACTLY ONE token from: {knowledge_node, risk_node, control_node, audit_facilitator}

Rules:
- audit_facilitator: audit processes, audit findings, audit documentation
- risk_node: risk management, risk register, risk matrices, risk generation
- control_node: security controls, control generation, control library, control implementation, Annex A controls
- knowledge_node: ISO 27001 clauses, information security standards, compliance guidance (not controls)

Output only the single token, no other text.
"""
            
            try:
                response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history)
                routing_decision = response_content.strip().lower()
            except Exception as e:
                print(f"Error in orchestrator LLM call: {e}")
                routing_decision = "knowledge_node"
    
    # Strict validation - accept only valid labels
    valid_labels = ["audit_facilitator", "risk_node", "control_node", "knowledge_node"]
    if routing_decision not in valid_labels:
        # Fallback logic
        if any(kw in user_text_lower for kw in ["control", "controls", "security control", "annex a"]):
            routing_decision = "control_node"
        elif any(kw in user_text_lower for kw in ["risk", "matrix", "likelihood", "impact"]):
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
            "is_risk_knowledge_related": False,
            "control_generation_requested": False,
            "generated_controls": [],
            "is_control_related": False,
            "control_target": "",
            "control_parameters": {}
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
            "is_risk_knowledge_related": False,
            "control_generation_requested": False,
            "generated_controls": [],
            "is_control_related": False,
            "control_target": "",
            "control_parameters": {}
        }
    elif routing_decision == "control_node":
        return {
            "input": state["input"],
            "output": "",
            "conversation_history": conversation_history,
            "risk_context": risk_context,
            "user_data": user_data,
            "active_mode": "control_node",
            "risk_generation_requested": False,
            "risk_register_requested": False,
            "matrix_recommendation_requested": False,
            "is_audit_related": False,
            "is_risk_related": False,
            "is_risk_knowledge_related": False,
            "control_generation_requested": False,
            "generated_controls": [],
            "is_control_related": True,
            "control_target": "",
            "control_parameters": {}
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
            "is_risk_knowledge_related": False,
            "control_generation_requested": False,
            "generated_controls": [],
            "is_control_related": False,
            "control_target": "",
            "control_parameters": {}
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
# Control nodes
builder.add_node("control_node", control_node)
builder.add_node("generate_control_node", control_generate_node)
builder.add_node("control_library_node", control_library_node)
builder.add_node("control_knowledge_node", control_knowledge_node)
builder.set_entry_point("orchestrator")

# Add conditional routing from orchestrator (two-level funnel)
def orchestrator_routing(state: LLMState) -> str:
    if state.get("is_audit_related", False):
        return "risk_node"  # Temporary routing to risk_node until audit_facilitator is implemented
    elif state.get("is_control_related", False):
        return "control_node"
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
    "risk_node": "risk_node",  # Route to risk sub-router for all risk-related queries
    "control_node": "control_node"  # Route to control sub-router for all control-related queries
})

def route_control_three_way(state: LLMState) -> str:
    """
    Fixed three-way routing function that properly handles all control sub-domains
    """
    control_target = state.get("control_target", "control_library_node")
    
    print(f"DEBUG: Control three-way routing - target: {control_target}")
    
    # Handle clarification state - stay in control node for another round
    if control_target == "clarify":
        return "end"
    
    # Route to appropriate sub-domain
    if control_target == "generate_control_node":
        return "generate_control_node"
    elif control_target == "control_knowledge_node":
        return "control_knowledge_node"
    elif control_target == "control_library_node":
        return "control_library_node"
    
    # Default fallback
    print(f"DEBUG: Unknown control target '{control_target}', defaulting to control_library_node")
    return "end"

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

# Add control routing conditional edges
builder.add_conditional_edges("control_node", route_control_three_way, {
    "control_node": "control_node",  # For clarifications, loop back
    "generate_control_node": "generate_control_node",
    "control_library_node": "control_library_node", 
    "control_knowledge_node": "control_knowledge_node",
    "end": END
})
builder.add_edge("generate_control_node", END)
builder.add_edge("control_library_node", END)
builder.add_edge("control_knowledge_node", END)

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
        "is_risk_knowledge_related": False,
        "control_generation_requested": False,
        "is_control_related": False,
        "control_target": "",
        "control_parameters": {}
    }
    
    # Use thread_id for memory persistence within the session
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(state, config)
    return result["output"], result["conversation_history"], result["risk_context"], result["user_data"]


GREETING_MESSAGE = """Welcome to the Risk Management Agent! I'm here to help your organization with comprehensive risk assessment, compliance management, and risk mitigation strategies. 

I can assist you with identifying operational, financial, strategic, and compliance risks, as well as provide guidance on industry regulations and best practices. 

What specific risk management challenges or compliance requirements would you like to discuss today?"""