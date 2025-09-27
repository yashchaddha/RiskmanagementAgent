import os
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langsmith import traceable

from dependencies import get_llm
from models import LLMState, AuditProgress, AuditItem
from prompt_utils import load_prompt
from audit_tools import (
    get_audit_progress,
    get_next_audit_item,
    list_audit_items,
    submit_audit_answer,
    skip_audit_item,
    reset_audit_item,
    delete_audit_item,
)
from rag_tools import knowledge_base_search
from database import AuditDatabaseService


load_dotenv()

LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")


def _progress_to_summary(progress: Optional[AuditProgress]) -> str:
    if not progress:
        return "No assessment items found yet."
    return (
        f"{progress.answered} answered, {progress.pending} pending, {progress.skipped} skipped "
        f"out of {progress.total} total"
    )


def _item_to_context(item: Optional[AuditItem]) -> Dict[str, Any]:
    if not item:
        return {}
    return item.dict()


def _safe_title(item: Optional[AuditItem]) -> str:
    if not item:
        return "All clauses are complete"
    return item.title or ""


def _safe_reference(item: Optional[AuditItem]) -> str:
    if not item:
        return "None"
    return item.iso_reference or "Unknown reference"


def _safe_description(item: Optional[AuditItem]) -> str:
    if not item:
        return "Every clause appears to be answered."
    return item.description or ""


@traceable(project_name=LANGSMITH_PROJECT_NAME, name="audit_facilitator_node")
def audit_facilitator_node(state: LLMState) -> LLMState:
    print("Audit Facilitator Node Activated")

    user_input = state.get("input", "") or ""
    conversation_history = state.get("conversation_history", []) or []
    user_data = state.get("user_data", {}) or {}
    user_id = user_data.get("username") or user_data.get("user_id") or ""

    progress_result = AuditDatabaseService.get_progress_summary(user_id)
    progress_data = progress_result.data if progress_result.success else None
    if progress_data and not isinstance(progress_data, AuditProgress):
        progress_data = AuditProgress(**progress_data)

    next_item_result = AuditDatabaseService.get_next_actionable_item(user_id)
    next_item = next_item_result.data if next_item_result.success else None
    if next_item and not isinstance(next_item, AuditItem):
        next_item = AuditItem(**next_item)

    progress_summary = _progress_to_summary(progress_data)
    system_prompt = load_prompt(
        "audit_facilitator_system.txt",
        {
            "organization_name": user_data.get("organization_name", "the organization"),
            "progress_summary": progress_summary,
            "next_clause_reference": _safe_reference(next_item),
            "next_clause_title": _safe_title(next_item),
            "next_clause_description": _safe_description(next_item),
        },
    )

    model = get_llm()
    tools_list = [
        get_audit_progress,
        get_next_audit_item,
        list_audit_items,
        submit_audit_answer,
        skip_audit_item,
        reset_audit_item,
        delete_audit_item,
        knowledge_base_search,
    ]
    llm = model.bind_tools(tools_list)
    tool_registry = {tool.name: tool for tool in tools_list}

    messages = [SystemMessage(content=system_prompt)]
    recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
    for turn in recent_history:
        if turn.get("user"):
            messages.append(HumanMessage(content=turn["user"]))
        if turn.get("assistant"):
            messages.append(AIMessage(content=turn["assistant"]))
    messages.append(HumanMessage(content=user_input))

    MAX_TOOL_STEPS = 8
    final_ai: Optional[AIMessage] = None

    try:
        for _ in range(MAX_TOOL_STEPS):
            ai_msg = llm.invoke(messages)
            messages.append(ai_msg)
            final_ai = ai_msg

            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                break

            for call in tool_calls:
                tool_name = call.get("name")
                call_args = call.get("args", {})

                if tool_name not in tool_registry:
                    messages.append(
                        ToolMessage(
                            content=f'{{"error":"unknown_tool","name":"{tool_name}"}}',
                            tool_call_id=call.get("id"),
                        )
                    )
                    continue

                try:
                    if "user_id" not in call_args:
                        call_args["user_id"] = user_id
                    result = tool_registry[tool_name].invoke(call_args)
                except Exception as exc:  # noqa: BLE001
                    result = {"success": False, "error": str(exc)}

                import json as _json

                payload = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False)
                if len(payload) > 8000:
                    payload = payload[:8000] + "…"

                messages.append(
                    ToolMessage(
                        content=payload,
                        tool_call_id=call.get("id"),
                        name=tool_name,
                    )
                )

        final_text = ""
        if final_ai and getattr(final_ai, "content", None):
            if isinstance(final_ai.content, list):
                final_text = " ".join(
                    part.content if hasattr(part, "content") else str(part)
                    for part in final_ai.content
                    if part
                )
            else:
                final_text = str(final_ai.content)

        if not final_text.strip():
            final_text = (
                "I'm ready to help you work through your ISO 27001 clauses. "
                "Let me know when you're ready to review the next item or need clarification."
            )

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]

        progress_dict = progress_data.dict() if isinstance(progress_data, AuditProgress) else {}
        next_item_dict = _item_to_context(next_item)

        updated_risk_context = state.get("risk_context", {}) or {}
        if progress_dict:
            updated_risk_context["audit"] = progress_dict
        elif "audit" in updated_risk_context:
            updated_risk_context.pop("audit")

        if next_item_dict:
            updated_risk_context["audit_next_item"] = next_item_dict
        elif "audit_next_item" in updated_risk_context:
            updated_risk_context.pop("audit_next_item")

        audit_context = {
            "next_item": next_item_dict,
            "last_updated": datetime.utcnow().isoformat(),
            "progress": progress_dict,
        }

        # Flag completion for downstream nodes
        if progress_data and progress_data.pending == 0 and progress_data.skipped == 0:
            audit_context["all_completed"] = True
            updated_risk_context["audit_complete"] = True
        elif "audit_complete" in updated_risk_context:
            updated_risk_context.pop("audit_complete")

        return {
            **state,
            "output": final_text,
            "conversation_history": updated_history,
            "risk_context": updated_risk_context,
            "user_data": user_data,
            "active_mode": "audit_facilitator",
            "audit_session_active": True,
            "audit_context": audit_context,
            "audit_progress": progress_dict,
        }

    except Exception as exc:  # noqa: BLE001
        error_message = (
            "I ran into a problem while helping with the audit. "
            "Please try again or ask for the next clause."
        )
        print(f"Error in audit facilitator node: {exc}")
        updated_history = conversation_history + [{"user": user_input, "assistant": error_message}]

        return {
            **state,
            "output": error_message,
            "conversation_history": updated_history,
            "active_mode": "audit_facilitator",
            "audit_session_active": True,
        }
