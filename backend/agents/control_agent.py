import os
import random
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dependencies import get_llm
from agent import make_llm_call_with_history
from rag_tools import semantic_risk_search, fetch_controls_by_id, knowledge_base_search, semantic_control_search
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
    Simplified control intent classifier that returns one of three tokens:
    - generate_control: Generate new controls
    - control_library: Search existing controls
    - control_knowledge: Answer questions about controls
    Or asks a clarifying question if intent is unclear.
    """
    print("Control Node Activated")
    
    user_input = state.get("input", "").strip()
    conversation_history = state.get("conversation_history", [])
    user_data = state.get("user_data", {})

    # Override from prompts folder if available
    system_prompt = """
    You are a control routing specialist for a internal control management.
    Based on the user's input, user's intent and the conversation history respond with exactly ONE of these three tokens:
    - generate_control: If the user wants to create/generate new controls for risks (this node will directly create the controls)
    - control_library: If the user wants to search/browse existing controls
    - control_knowledge: If the user is asking questions about controls or implementation
    
    If the user's intent is unclear or doesn't match any of these categories, respond with a concise clarifying question.
    
    Examples:
    "Create controls for my operational risks" → generate_control
    "Show me all my controls for data privacy" → control_library
    "How do I implement access control in my organization?" → control_knowledge
    "I want to check my cybersecurity posture" → "Could you clarify if you'd like to review your existing controls, generate new controls, or learn about control implementation for cybersecurity?"
    """

    try:
        response_content = make_llm_call_with_history(system_prompt, user_input, conversation_history).strip()
        
        # Check if response is one of the valid tokens
        if response_content in ["generate_control", "control_library", "control_knowledge"]:
            print(f"DEBUG: Control node routing to: {response_content}")
            
            # Set control-related flags
            state["is_control_related"] = True
            
            if response_content == "generate_control":
                state["control_target"] = "generate_control_node"
                state["control_generation_requested"] = True
                return state
            elif response_content == "control_library":
                state["control_target"] = "control_library_node"
                state["control_generation_requested"] = False
                return state
            elif response_content == "control_knowledge":
                state["control_target"] = "control_knowledge_node"
                state["control_generation_requested"] = False
                return state
        
        # If we get here, the response was a clarifying question
        clarifying_question = response_content
        
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
    """Conversational control library assistant for searching and managing user's controls (tool-calling version)."""
    print("Control Library Node Activated")

    user_input = state.get("input", "") or ""
    user_data = state.get("user_data", {}) or {}
    conversation_history = state.get("conversation_history", []) or []
    user_id = user_data.get("username") or user_data.get("user_id") or ""
    search_intent_prompt = load_prompt("control_library_assistant.txt", {"user_id": user_id})

    # 1) Build messages (keep context tight)
    messages = [SystemMessage(content=search_intent_prompt)]
    recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
    for ex in recent_history:
        if ex.get("user"):
            messages.append(HumanMessage(content=ex["user"]))
        if ex.get("assistant"):
            messages.append(AIMessage(content=ex["assistant"]))
    messages.append(HumanMessage(content=user_input))

    # 2) Bind tools directly (predictable tool-calling; small prompt)
    model = get_llm()
    tools_list = [semantic_control_search, semantic_risk_search]


    llm = model.bind_tools(tools_list)
    tool_registry = {t.name: t for t in tools_list}

    # 3) Small deterministic loop (no planner). The model decides tools; we execute them.
    MAX_TOOL_STEPS = 6
    final_ai = None
    try:
        for _ in range(MAX_TOOL_STEPS):
            ai_msg = llm.invoke(messages)
            messages.append(ai_msg)
            final_ai = ai_msg

            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                break  # model produced a final answer

            for call in tool_calls:
                tname = call.get("name")
                if tname not in tool_registry:
                    # Return a tool error back to the model
                    messages.append(ToolMessage(
                        content=f'{{"error":"unknown_tool","name":"{tname}"}}',
                        tool_call_id=call.get("id"),
                    ))
                    continue

                # Execute tool with model-proposed args
                try:
                    result = tool_registry[tname].invoke(call.get("args", {}))
                except Exception as e:
                    result = {"error": str(e)}

                # IMPORTANT: return compact JSON/string to the model
                import json
                payload = result
                if not isinstance(payload, str):
                    payload = json.dumps(payload, ensure_ascii=False)
                # Optional: hard cap payload size if a tool misbehaves
                if len(payload) > 8000:
                    payload = payload[:8000] + "…"

                messages.append(ToolMessage(
                    content=payload,
                    tool_call_id=call.get("id"),
                    name=tname,
                ))

        # 4) Extract final text
        final_text = ""
        if final_ai and getattr(final_ai, "content", None):
            if isinstance(final_ai.content, list):
                final_text = " ".join(part.content if hasattr(part, "content") else str(part)
                                      for part in final_ai.content if part)
            else:
                final_text = str(final_ai.content)

        if not final_text.strip():
            # Try to synthesize an answer directly from the latest tool results
            # Prefer the most recent semantic_control_search or fetch_controls_by_id output
            latest_tool_payload = None
            latest_tool_name = None
            for m in reversed(messages):
                if isinstance(m, ToolMessage) and isinstance(m.content, str):
                    latest_tool_payload = m.content
                    latest_tool_name = getattr(m, "name", None)
                    # Use the most recent tool result
                    break

            synthesized_text = ""
            if latest_tool_payload:
                try:
                    parsed = json.loads(latest_tool_payload)
                    # Handle shortlist from semantic_control_search
                    if isinstance(parsed, dict) and parsed.get("hits"):
                        hits = parsed.get("hits", [])
                        if hits:
                            top = hits[:3]
                            lines = []
                            for h in top:
                                cid = h.get("control_id") or h.get("id")
                                title = h.get("title") or h.get("control_title")
                                summary = h.get("summary") or h.get("control_text") or h.get("description")
                                if summary:
                                    summary = (summary.replace("\n", " ").strip())
                                    if len(summary) > 180:
                                        summary = summary[:180] + "…"
                                line = f"• {cid}: {title} — {summary}" if (cid and title) else None
                                if line:
                                    lines.append(line)
                            if lines:
                                synthesized_text = (
                                    "Here are the top controls I found:\n" + "\n".join(lines)
                                )
                    # Handle detailed fetch_controls_by_id response
                    if not synthesized_text and isinstance(parsed, dict) and parsed.get("controls"):
                        ctrls = parsed.get("controls", [])
                        if ctrls:
                            top = ctrls[:3]
                            lines = []
                            for c in top:
                                cid = c.get("control_id")
                                title = c.get("title") or c.get("control_title")
                                desc = c.get("description") or c.get("control_description")
                                if desc:
                                    desc = (desc.replace("\n", " ").strip())
                                    if len(desc) > 180:
                                        desc = desc[:180] + "…"
                                line = f"• {cid}: {title} — {desc}" if (cid and title) else None
                                if line:
                                    lines.append(line)
                            if lines:
                                synthesized_text = (
                                    "Here are the top matching controls:\n" + "\n".join(lines)
                                )
                except Exception:
                    # If parsing fails, fall back to default message below
                    pass

            if synthesized_text:
                final_text = synthesized_text
            else:
                final_text = (
                    "I’ve opened your control library. Try: “find controls for Annex A.8.30” "
                    "or “list top controls mapped to data breach risks.”"
                )

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]
        return {
            "output": final_text,
            "conversation_history": updated_history,
            "user_data": user_data,
            "control_generation_requested": False,
        }

    except Exception as e:
        print(f"control_library_node error: {e}")
        error_response = (
            "I understand you want your control library. It’s open. "
            "You can ask me to search it (e.g., “find data privacy controls”)."
        )
        return {
            "output": error_response,
            "conversation_history": conversation_history + [{"user": user_input, "assistant": error_response}],
            "user_data": user_data,
            "control_generation_requested": False,
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

        # Switch to bind_tools deterministic loop (consistent with control_library_node)
        tools_list = [knowledge_base_search, semantic_control_search]
        llm = model.bind_tools(tools_list)
        tool_registry = {t.name: t for t in tools_list}

        MAX_TOOL_STEPS = 6
        final_ai = None
        for _ in range(MAX_TOOL_STEPS):
            ai_msg = llm.invoke(messages)
            messages.append(ai_msg)
            final_ai = ai_msg

            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                break

            for call in tool_calls:
                tname = call.get("name")
                if tname not in tool_registry:
                    messages.append(ToolMessage(
                        content=f'{{"error":"unknown_tool","name":"{tname}"}}',
                        tool_call_id=call.get("id"),
                    ))
                    continue
                try:
                    result = tool_registry[tname].invoke(call.get("args", {}))
                except Exception as e:
                    result = {"error": str(e)}

                import json as _json
                payload = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False)

                messages.append(ToolMessage(
                    content=payload,
                    tool_call_id=call.get("id"),
                    name=tname,
                ))

        # Extract final text
        final_text = ""
        if final_ai and getattr(final_ai, "content", None):
            if isinstance(final_ai.content, list):
                final_text = " ".join(part.content if hasattr(part, "content") else str(part)
                                      for part in final_ai.content if part)
            else:
                final_text = str(final_ai.content)

        if not final_text.strip():
            final_text = (
                "I couldn't retrieve knowledge entries right now. Please try again."
            )
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
    system_prompt = f"""You are a control generation specialist assisting users in creating ISO 27001 controls.

USER CONTEXT:
- User ID: {user_id}
- Organization: {user_organization}  
- Location: {user_location}
- Domain: {user_domain}

TOOLS AVAILABLE:
1. semantic_risk_search: Search user's risk register for relevant risks
2. knowledge_base_search: Search ISO 27001 knowledge base for control information

PROCESS:
1. Analyze user input to understand their control generation needs
2. Determine risk source:
   - If user wants to search their risk register → use semantic_risk_search
   - If user provides direct risk description → skip search, use description directly
3. For identified risks, generate appropriate controls
4. Use knowledge_base_search to map controls to ISO 27001 Annex A
5. Return results in the EXACT JSON format specified below

CRITICAL: You MUST respond with ONLY valid JSON. No explanatory text before or after. No markdown code blocks. Just pure JSON.

JSON OUTPUT FORMAT (REQUIRED):
{{
  "response_to_user": "Brief explanation of what controls were generated and why",
  "controls": [
    {{
      "control_title": "Clear, specific control title",
      "control_description": "Detailed description addressing the specific risk",
      "objective": "Business objective and purpose of this control",
      "annexA_map": [
        {{"id": "A.X.Y", "title": "ISO 27001 Annex A control title"}}
      ],
      "linked_risk_ids": ["RISK-ID-123"],
      "owner_role": "CISO|IT Manager|Security Officer|Data Protection Officer",
      "process_steps": [
        "Specific implementation step 1",
        "Specific implementation step 2",
        "Specific implementation step 3"
      ],
      "evidence_samples": [
        "Audit document or evidence example 1",
        "Audit document or evidence example 2",
        "Audit document or evidence example 3"
      ],
      "metrics": [
        "Measurable KPI or metric 1",
        "Measurable KPI or metric 2"
      ],
      "frequency": "Monthly|Quarterly|Annually|Continuous",
      "policy_ref": "Related organizational policy reference",
      "status": "Planned",
      "rationale": "Why this control is necessary for the specific risk",
      "assumptions": "Any assumptions made (or empty string)"
    }}
  ]
}}

IMPORTANT RULES:
- Generate 2-4 controls per risk
- linked_risk_ids should be empty array [] if user provided direct description
- annexA_map must contain real ISO 27001 Annex A controls from knowledge base
- All JSON fields are required (use empty string "" for optional text fields)
- Response must be valid JSON that can be parsed by json.loads()
- No text outside the JSON structure"""

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

        # Replace create_react_agent with bind_tools deterministic loop
        tools_list = [semantic_risk_search, knowledge_base_search]
        llm = model.bind_tools(tools_list)
        tool_registry = {t.name: t for t in tools_list}

        MAX_TOOL_STEPS = 8
        final_ai = None
        debug_tool_calls = []
        for _ in range(MAX_TOOL_STEPS):
            ai_msg = llm.invoke(messages)
            messages.append(ai_msg)
            final_ai = ai_msg

            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                break

            for call in tool_calls:
                debug_tool_calls.append(call)
                tname = call.get("name")
                if tname not in tool_registry:
                    messages.append(ToolMessage(
                        content=f'{{"error":"unknown_tool","name":"{tname}"}}',
                        tool_call_id=call.get("id"),
                    ))
                    continue
                try:
                    result = tool_registry[tname].invoke(call.get("args", {}))
                except Exception as e:
                    result = {"error": str(e)}

                import json as _json
                payload = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False)
                if len(payload) > 14000:
                    payload = payload[:14000] + "…"

                messages.append(ToolMessage(
                    content=payload,
                    tool_call_id=call.get("id"),
                    name=tname,
                ))

        # Print tool calls for debugging
        for tool_call in debug_tool_calls:
            print(f"Tool Call: {tool_call}")

        # Extract final assistant content
        response_content = ""
        if final_ai and getattr(final_ai, "content", None):
            if isinstance(final_ai.content, list):
                response_content = " ".join(part.content if hasattr(part, "content") else str(part)
                                             for part in final_ai.content if part)
            else:
                response_content = str(final_ai.content)
        
        print(f"LLM Response received: {response_content[:100]}...")
        
        # Update conversation history
        updated_history = conversation_history + [
            {"user": user_input, "assistant": response_content}
        ]

        # add a control_id to each control in the format - CONTROL-<6 digit random number>
        def _extract_json(text: str) -> str:
            """Extract JSON from LLM response, handling various formats and cleaning up common issues."""
            if not text:
                raise ValueError("Empty response text")
            
            t = text.strip()
            
            # Remove markdown code blocks
            if t.startswith("```json") and t.endswith("```"):
                t = t[7:-3].strip()
            elif t.startswith("```") and t.endswith("```"):
                t = t[3:-3].strip()
            
            # Handle common LLM prefixes
            prefixes_to_remove = [
                "Here's the JSON response:",
                "Here is the JSON:",
                "JSON response:",
                "Response:",
            ]
            for prefix in prefixes_to_remove:
                if t.lower().startswith(prefix.lower()):
                    t = t[len(prefix):].strip()
            
            # Find JSON object boundaries
            start = t.find("{")
            if start == -1:
                raise ValueError("No JSON object found in response")
            
            # Find the matching closing brace
            depth = 0
            for i in range(start, len(t)):
                if t[i] == '{':
                    depth += 1
                elif t[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_str = t[start:i+1]
                        # Basic validation - try to parse it
                        try:
                            json.loads(json_str)
                            return json_str
                        except json.JSONDecodeError as e:
                            raise ValueError(f"Invalid JSON structure: {e}")
            
            raise ValueError("Unbalanced JSON braces")

        content = response_content.strip()        
        try:
            content = _extract_json(content)
            print(f"Extracted JSON: {content[:200]}...")
        except Exception as e:
            print(f"JSON extraction failed: {e}")
            # Try to use the original content as fallback
            if not content.strip().startswith("{"):
                # If it doesn't look like JSON at all, create a fallback response
                fallback_response = {
                    "response_to_user": content if content.strip() else "I apologize, but I couldn't generate controls in the proper format. Please try again with more specific details.",
                    "controls": []
                }
                content = json.dumps(fallback_response)

        # Ensure defaults so we don't reference before assignment on error paths
        response_to_user = ""
        controls = []
        try:
            output = json.loads(content)
            
            # Validate the structure
            if not isinstance(output, dict):
                raise ValueError("Response must be a JSON object")
            if "response_to_user" not in output:
                output["response_to_user"] = "I've generated controls based on your request."
            
            if "controls" not in output:
                output["controls"] = []
            
            controls = output.get("controls", [])
            response_to_user = output.get("response_to_user", "")
            
            # Validate controls structure
            if not isinstance(controls, list):
                print("Warning: 'controls' field is not an array, converting to empty array")
                controls = []
            
            # Add control IDs and validate each control
            valid_controls = []
            for i, control in enumerate(controls):
                if not isinstance(control, dict):
                    print(f"Warning: Control {i} is not an object, skipping")
                    continue
                
                # Add required fields if missing
                required_fields = [
                    "control_title", "control_description", "objective", 
                    "annexA_map", "linked_risk_ids", "owner_role", 
                    "process_steps", "evidence_samples", "metrics", 
                    "frequency", "policy_ref", "status", "rationale", "assumptions"
                ]
                
                for field in required_fields:
                    if field not in control:
                        if field in ["annexA_map", "linked_risk_ids", "process_steps", "evidence_samples", "metrics"]:
                            control[field] = []
                        else:
                            control[field] = ""
                
                # Add control ID
                control["control_id"] = f"CONTROL-{random.randint(100000, 999999)}"
                valid_controls.append(control)
            
            controls = valid_controls
            print(f"Validated and processed {len(controls)} controls")
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Content that failed to parse: {content[:500]}...")
            state["control_generation_requested"] = False
            state["conversation_history"] = updated_history
            fallback = "I encountered an issue generating the controls in the proper format. The response wasn't structured correctly. Please try again with more specific details about the risks you'd like controls for."
            state["output"] = fallback
            return state
            
        except Exception as e:
            print(f"Unexpected error processing controls: {e}")
            state["control_generation_requested"] = False
            state["conversation_history"] = updated_history
            fallback = f"I encountered an unexpected error while processing the controls: {str(e)}. Please try again."
            state["output"] = fallback
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
