import os
import random
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dependencies import get_llm
from agent import make_llm_call_with_history
from rag_tools import semantic_risk_search, get_risk_profiles, knowledge_base_search, semantic_control_search
from models import LLMState
import json
import uuid
import time
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from database import ControlDatabaseService, RiskDatabaseService
import traceback
from prompt_utils import load_prompt

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

    # Override from prompts folder if available
    system_prompt = load_prompt("control_classifier.txt")

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

@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_library_node")
def control_library_node(state: LLMState) -> LLMState:
    """Conversational control library assistant for searching and managing user's controls"""
    print("Control Library Node Activated")
    
    user_input = state.get("input", "")
    user_data = state.get("user_data", {})
    conversation_history = state.get("conversation_history", [])
    user_id = user_data.get("username") or user_data.get("user_id") or ""
    model = get_llm()
    search_intent_prompt = load_prompt("control_library_assistant.txt", {"user_id": user_id})

    try:
        messages = [SystemMessage(content=search_intent_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for ex in recent_history:
            if ex.get("user"):
                messages.append(HumanMessage(content=ex["user"]))
            if ex.get("assistant"):
                messages.append(AIMessage(content=ex["assistant"]))

        messages.append(HumanMessage(content=user_input))
        # Create ReAct agent with all required tools
        agent = create_react_agent(
            model=model,
            tools=[semantic_control_search, knowledge_base_search, semantic_risk_search]
        )

        # Track tool calls
        tool_calls = []
        result = agent.invoke({"messages": messages})
        
        # Extract tool calls from the result
        for message in result.get("messages", []):
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls.extend(message.tool_calls)
            elif isinstance(message, ToolMessage):
                tool_calls.append(message)
        
        # Print tool calls for debugging
        for tool_call in tool_calls:
            print(f"Tool Call: {tool_call}")
        
        # Get the final result
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
        system_prompt = load_prompt(
            "control_knowledge_specialist.txt",
            {
                "user_id": user_data.get("username") or user_data.get("user_id") or "",
                "user_organization": user_organization,
                "user_location": user_location,
                "user_domain": user_domain,
            },
        )

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


@traceable(project_name=LANGSMITH_PROJECT_NAME, name="control_generate_node")
def control_generate_node(state: LLMState) -> LLMState:
    """
    Control generation node.
    1. From the user input, determine the risk source (direct description vs search user's risk register).
    2. If user has given the description directly get the description and generate controls for it.
    3. If user wants to search their risk register, call the RAG tool semantic_risk_search to find relevant risks.
    4. Then for the identified risks, generate controls for them.
    5. Map the generated controls to ISO 27001 Annex A by calling knowledge_base_search.
    6. Return the generated controls as JSON and update the state.
    """

    print("Control Generate Node Activated")
    conversation_history = state.get("conversation_history", [])
    user_data = state.get("user_data", {})
    user_id = user_data.get("username")
    user_input = state.get("input", "").strip()
    user_organization = user_data.get("organization_name", "Unknown").strip()
    user_location = user_data.get("location", "Unknown").strip()
    user_domain = user_data.get("domain", "Unknown").strip()

    model = get_llm()
    system_prompt = f"""
    You are a control generation specialist assisting users in creating ISO 27001 controls.
    Your task is to generate relevant and effective controls based on the user's risk context and organizational details.
    You have access to the following tools:
    1. semantic_risk_search: Search the user's risk register to find relevant risks based on a query.
    2. knowledge_base_search: Search an ISO 27001 knowledge base to find relevant control information.

    USER CONTEXT:
    - User ID: {user_id}
    - Organization: {user_organization}
    - Location: {user_location}
    - Domain: {user_domain}

    Follow the PROCESS below to generate controls:
    PROCESS:
    1. Analyze the user's input and recent conversation history to understand their needs.
    2. Determine if the user has provided a direct risk description or wants to search their risk register.
       - If they want to search their register, use semantic_risk_search to find relevant risks.
       - If a direct description is provided, do not call semantic_risk_search, directly generate controls for the given risk with linked_risk_ids: [] i.e. no risk id needed as the user has provided a description.
    3. For each risk, generate controls that address the risk effectively.
    4. Use knowledge_base_search to find relevant ISO 27001 control information to map the generated controls to Annex A.
    5. Compile the generated controls into a JSON array with the following fields:    
        1. control_title: Clear, specific control title
        2. control_description: Detailed description of what this control addresses for this risk
        3. objective: Business objective and purpose of the control
        4. annexA_map: Array of relevant ISO 27001:2022 Annex A mappings with id and title
        5. linked_risk_ids: Array containing the risk ID this control addresses
        6. owner_role: Suggested role responsible for this control (e.g., "CISO", "IT Manager", "Security Officer")
        7. process_steps: Array of 3-5 specific implementation steps
        8. evidence_samples: Array of 3-5 examples of evidence/documentation for this control
        9. metrics: Array of 2-4 measurable KPIs or metrics to track control effectiveness
        10. frequency: How often the control is executed/reviewed (e.g., "Quarterly", "Monthly", "Annually")
        11. policy_ref: Reference to related organizational policy
        12. status: Set to "Planned" for new controls
        13. rationale: Why this control is necessary for mitigating the specific risk
        14. assumptions: Any assumptions made (can be empty string if none)
    6. Ensure the ISO 27001 Annex A mappings are accurate and relevant.
    7. Return the generated controls and the response text as STRICTLY JSON ONLY. No additional text. If no controls can be generated, return response_to_user with an explanation but still return valid JSON with an empty controls array. and follow the RESPONSE FORMAT below.

JSON RESPONSE FORMAT:
{{
  "response_to_user": "...",
  "controls": [
    {{
      "control_title": "...",
      "control_description": "...",
      "objective": "...",
      "annexA_map": [
        {{"id": "A.X.Y", "title": "..."}}
      ],
      "linked_risk_ids": [],
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
}}
"""

    try:
        print(f"control_generate_node: user_id={user_id}, input_len={len(user_input)}")
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
            tools=[semantic_risk_search, knowledge_base_search],
        )
        result = agent.invoke({"messages": messages})
        # Extract final assistant content
        # get the tool calls for debugging
        tool_calls = []
        for message in result.get("messages", []):
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls.extend(message.tool_calls)
            elif isinstance(message, ToolMessage):
                tool_calls.append(message)
        
        # Print tool calls for debugging
        for tool_call in tool_calls:
            print(f"Tool Call: {tool_call}")

        final_msg = result["messages"][-1]
        response_content = getattr(final_msg, "content", getattr(final_msg, "text", "")) or ""
        
        print(f"LLM Response received: {response_content[:100]}...")
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_content}
        ]

        # add a control_id to each control in the format - CONTROL-<6 digit random number>
        content = response_content.strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        elif content.startswith("```") and content.endswith("```"):
            content = content[3:-3].strip()
        print(f"Raw response content extracted: {content}")

        try:
            output = json.loads(content)
            controls = output.get("controls", [])
            response_to_user = output.get("response_to_user", "")
            for control in controls:
                control["control_id"] = f"CONTROL-{random.randint(100000, 999999)}"
            print(f"Parsed controls with IDs: {controls}")
        except json.JSONDecodeError:
            print("Failed to parse JSON from response content")
            state["control_generation_requested"] = False
            state["output"] = response_to_user or "I couldn't generate controls based on the provided information. Please try rephrasing or providing more details."
            return state
        except Exception as e:
            print(f"Unexpected error parsing controls: {e}")
            state["control_generation_requested"] = False
            state["output"] = response_to_user or "I couldn't generate controls based on the provided information. Please try rephrasing or providing more details."
            return state
        
        state["risk_context"] = state.get("risk_context", {}) or {}
        state["risk_context"]["generated_controls"] = controls
        state["generated_controls"] = controls
        print(f"control_generate_node: returning {len(controls)} controls")
        state["output"] = response_to_user or f"I've generated {len(controls)} controls for you."
        return {
            **state,
            "conversation_history": updated_history,
            "control_generation_requested": False
        }
    except Exception as e:
        print(f"Error in control_generate_node: {str(e)}")
        state["control_generation_requested"] = False
        state["output"] = f"Error generating controls: {str(e)}"
        return state
