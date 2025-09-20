import os
from dotenv import load_dotenv
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from dependencies import get_llm
from agent import make_llm_call_with_history
from rag_tools import (
    semantic_risk_search,
    get_risk_profiles,
)
from graph_tools import execute_cypher, get_field_values
from models import LLMState
import json
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from database import RiskProfileDatabaseService
import traceback
from prompt_utils import load_prompt

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
        
        system_prompt = load_prompt("risk_intent_router.txt")

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
        system_prompt = load_prompt(
            "risk_generation_system.txt",
            {
                "user_id": user_id,
                "organization_name": organization_name,
                "location": location,
                "domain": domain,
            },
        )

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
        organization_name = user_data.get("organization_name") or risk_context.get("organization") or "your organization"
        organization_name = organization_name.strip() or "your organization"

        model = get_llm()
        system_prompt = load_prompt("risk_register_assistant.txt", {"user_id": user_id, "organization_name": organization_name}).strip()

        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for turn in recent_history:
            if turn.get("user"):
                messages.append(HumanMessage(content=turn["user"]))
            if turn.get("assistant"):
                messages.append(AIMessage(content=turn["assistant"]))

        messages.append(HumanMessage(content=user_input))

        # Use direct cypher execution with field value discovery for maximum search flexibility
        tools_list = [execute_cypher, get_field_values]

        llm = model.bind_tools(tools_list)
        tool_registry = {t.name: t for t in tools_list}

        max_steps = 4
        step = 0
        final_ai_msg = None

        while step < max_steps:
            step += 1
            print(f"Risk Register Node - Step {step}")
            ai_msg = llm.invoke(messages)
            tool_calls = getattr(ai_msg, "tool_calls", None)
            print(f"Tool calls in step {step}: {len(tool_calls) if tool_calls else 0}")

            if not tool_calls:
                print(f"No tool calls, setting final message: {ai_msg.content[:100] if hasattr(ai_msg, 'content') else 'No content'}")
                final_ai_msg = ai_msg
                break

            tool_messages = []
            for tc in tool_calls:
                name = tc.get("name")
                args = tc.get("args", {}) or {}
                call_id = tc.get("id")

                if name in tool_registry:
                    tool_func = tool_registry[name]
                    
                    # Align tool arguments with risk register prompt guidance
                    if name == "execute_cypher":
                        # Add org parameter if available for potential use in queries
                        if organization_name and organization_name != "your organization":
                            args.setdefault("org", organization_name)
                    elif name == "get_field_values":
                        # Default to Risk node type for risk register queries
                        args.setdefault("node_type", "Risk")

                    try:
                        if hasattr(tool_func, "invoke"):
                            tool_result = tool_func.invoke(args)
                        else:
                            tool_result = tool_func(**args)
                    except Exception as tool_err:
                        tool_result = {"error": f"{name} failed: {tool_err}"}

                    # Ensure tool result is JSON-serializable for ToolMessage content
                    try:
                        content_str = json.dumps(tool_result, default=str)
                    except Exception as ser_err:
                        # Fallback to a minimal safe representation
                        print(f"Serialization warning for tool '{name}': {ser_err}")
                        try:
                            content_str = json.dumps({
                                "success": tool_result.get("success", True) if isinstance(tool_result, dict) else True,
                                "count": tool_result.get("count", len(tool_result.get("results", []))) if isinstance(tool_result, dict) else 0,
                                "message": "Non-JSON types converted to string",
                                "data": str(tool_result)
                            })
                        except Exception:
                            content_str = str(tool_result)

                    tool_messages.append(
                        ToolMessage(
                            tool_call_id=call_id,
                            content=content_str
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
            print(f"Loop ended without final response, giving LLM final chance to respond")
            try:
                final_response = llm.invoke(messages)
                final_ai_msg = final_response
                print(f"Final LLM response: {final_response.content[:100] if hasattr(final_response, 'content') else 'No content'}")
            except Exception as e:
                print(f"Error getting final LLM response: {e}")

        if final_ai_msg is None:
            print("WARNING: final_ai_msg is None, falling back to generic message")
            final_text = (
                "I've opened your risk register. You can ask me to search it."
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

        prompt = load_prompt(
            "matrix_recommendation_prompt.txt",
            {
                "user_input": user_input,
                "org": org,
                "loc": loc,
                "dom": dom,
                "len(existing_risk_categories)": len(existing_risk_categories),
                "risk_categories_list": risk_categories_list,
            },
        )

        content = make_llm_call_with_history(prompt, user_input, conversation_history).strip()

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
        system_prompt = load_prompt(
            "risk_knowledge_specialist.txt",
            {
                "user_id": user_id,
                "user_data.get('organization_name', 'Unknown')": user_data.get(
                    "organization_name", "Unknown"
                ),
                "user_data.get('location', 'Unknown')": user_data.get(
                    "location", "Unknown"
                ),
                "user_data.get('domain', 'Unknown')": user_data.get(
                    "domain", "Unknown"
                ),
            },
        )

        # Build conversation history
        messages = [SystemMessage(content=system_prompt)]
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        for turn in recent_history:
            if turn.get("user"):
                messages.append(HumanMessage(content=turn["user"]))
            if turn.get("assistant"):
                messages.append(AIMessage(content=turn["assistant"]))
        messages.append(HumanMessage(content=user_input))

        # Use comprehensive graph reasoning tools for risk knowledge
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

