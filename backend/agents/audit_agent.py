import os
from datetime import datetime
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langsmith import traceable

from dependencies import get_llm
from models import LLMState, AuditProgress, AuditItem, AuditTypeProgress
from prompt_utils import load_prompt
from audit_tools import (
    get_audit_progress,
    get_annex_progress,
    get_next_audit_item,
    get_next_annex_item,
    list_audit_items,
    skip_audit_item,
    skip_annex_group,
    reset_audit_item,
    reset_annex_group,
    delete_audit_item,
    exclude_annex_item,
    reinstate_annex_item,
    exclude_annex_group,
    reinstate_annex_group,
)
from rag_tools import knowledge_base_search
from database import AuditDatabaseService


load_dotenv()

LANGSMITH_PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "risk-management-agent")

REQUEST_ANSWER_TOKEN = "[[REQUEST_CLAUSE_ANSWER]]"


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

    next_item = None


    phase_progress_result = AuditDatabaseService.get_phase_progress(user_id)
    clause_progress = None
    annex_progress = None
    if phase_progress_result.success and phase_progress_result.data:
        data = phase_progress_result.data
        if isinstance(data, dict):
            clause_progress = data.get("clauses")
            annex_progress = data.get("annexes")
        else:
            clause_progress = getattr(data, "clauses", None)
            annex_progress = getattr(data, "annexes", None)

    def _default_type_progress() -> AuditTypeProgress:
        return AuditTypeProgress(total=0, pending=0, answered=0, skipped=0, excluded=0)

    def _ensure_type_progress(value: Optional[Any]) -> AuditTypeProgress:
        if isinstance(value, AuditTypeProgress):
            return value
        if isinstance(value, dict):
            try:
                return AuditTypeProgress(**value)
            except Exception:  # noqa: BLE001
                return _default_type_progress()
        return _default_type_progress()

    clause_progress = _ensure_type_progress(clause_progress)
    annex_progress = _ensure_type_progress(annex_progress)

    clause_progress_dict = clause_progress.dict()
    annex_progress_dict = annex_progress.dict()
    clause_total = clause_progress_dict.get("total", 0)
    annex_total = annex_progress_dict.get("total", 0)
    previous_phase = state.get("audit_phase", "clauses") or "clauses"
    audit_phase = previous_phase
    phase_transition_note = ""

    clause_pending = clause_progress_dict.get("pending", 0)
    clause_skipped = clause_progress_dict.get("skipped", 0)
    clause_remaining = clause_pending + clause_skipped

    annex_pending = annex_progress_dict.get("pending", 0)
    annex_skipped = annex_progress_dict.get("skipped", 0)
    annex_remaining = annex_pending + annex_skipped

    if audit_phase == "clauses" and clause_remaining == 0 and clause_total > 0:
        if annex_total > 0:
            audit_phase = "annexes"
            phase_transition_note = ("All mandatory clauses are complete. Let's move on to Annex A controls when you're ready.")
    if audit_phase == "clauses" and clause_total == 0 and annex_total > 0:
        audit_phase = "annexes"
        if not phase_transition_note:
            phase_transition_note = ("No clause checklist is assigned, so we'll start directly with Annex A controls.")
    if audit_phase == "annexes" and annex_total == 0 and clause_total > 0:
        audit_phase = "clauses"
        phase_transition_note = ""

    if progress_data is None:
        combined_total = clause_total + annex_total
        combined_answered = clause_progress_dict.get("answered", 0) + annex_progress_dict.get("answered", 0)
        combined_skipped = clause_progress_dict.get("skipped", 0) + annex_progress_dict.get("skipped", 0)
        combined_pending = max(combined_total - combined_answered - combined_skipped, 0)
        progress_data = AuditProgress(total=combined_total, pending=combined_pending, answered=combined_answered, skipped=combined_skipped)

    clause_summary: str
    if clause_total or clause_progress_dict.get("answered", 0) or clause_skipped:
        clause_summary = (
            f"Clauses: {clause_progress_dict.get('answered', 0)} answered, "
            f"{clause_progress_dict.get('pending', 0)} pending, "
            f"{clause_progress_dict.get('skipped', 0)} skipped out of {clause_total}."
        )
    else:
        clause_summary = "Clauses: no clause checklist assigned."

    if annex_total or annex_progress_dict.get("excluded", 0) or annex_skipped:
        annex_summary_parts = [
            f"Annexes: {annex_progress_dict.get('answered', 0)} answered, ",
            f"{annex_progress_dict.get('pending', 0)} pending, ",
            f"{annex_progress_dict.get('skipped', 0)} skipped out of {annex_total} active controls.",
        ]
        if annex_progress_dict.get("excluded", 0):
            annex_summary_parts.append(f" {annex_progress_dict.get('excluded', 0)} excluded.")
        annex_summary = "".join(annex_summary_parts)
    else:
        annex_summary = "Annexes: no Annex A controls assigned."

    progress_summary = f"{clause_summary} {annex_summary}".strip()
    overall_progress_summary = _progress_to_summary(progress_data)
    if audit_phase == "annexes":
        next_item_result = AuditDatabaseService.get_next_item_by_type(user_id, "annex")
    else:
        next_item_result = AuditDatabaseService.get_next_item_by_type(user_id, "clause")

    next_item = next_item_result.data if next_item_result.success else None
    if next_item and not isinstance(next_item, AuditItem):
        next_item = AuditItem(**next_item)

    system_prompt = load_prompt(
        "audit_facilitator_system.txt",
        {
            "organization_name": user_data.get("organization_name", "the organization"),
            "progress_summary": progress_summary,
            "overall_progress": overall_progress_summary,
            "clause_summary": clause_summary,
            "annex_summary": annex_summary,
            "audit_phase": audit_phase,
            "phase_transition_note": phase_transition_note,
            "clause_remaining": clause_remaining,
            "annex_remaining": annex_remaining,
            "next_clause_reference": _safe_reference(next_item),
            "next_clause_title": _safe_title(next_item),
            "next_clause_description": _safe_description(next_item),
        },
    )

    model = get_llm()
    tools_list = [
        get_audit_progress,
        get_annex_progress,
        get_next_audit_item,
        get_next_annex_item,
        list_audit_items,
        skip_audit_item,
        skip_annex_group,
        reset_audit_item,
        reset_annex_group,
        delete_audit_item,
        exclude_annex_item,
        reinstate_annex_item,
        exclude_annex_group,
        reinstate_annex_group,
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
                call_args = call.get("args", {}) or {}
                call_args["user_id"] = user_id

                print(f"[AUDIT] Invoking tool {tool_name} with args {call_args}")

                if tool_name not in tool_registry:
                    messages.append(
                        ToolMessage(
                            content=f'{{"error":"unknown_tool","name":"{tool_name}"}}',
                            tool_call_id=call.get("id"),
                        )
                    )
                    print(f"[AUDIT][WARN] Unknown tool requested: {tool_name}")
                    continue

                try:
                    if tool_name in {"skip_audit_item", "reset_audit_item", "delete_audit_item"}:
                        identifier = call_args.get("item_id") or call_args.get("iso_reference")
                        resolved_item = None
                        if identifier:
                            identifier_str = str(identifier).strip()
                            candidates = [identifier_str]
                            identifier_lower = identifier_str.lower()
                            if identifier_lower.startswith("clause"):
                                trimmed = identifier_lower[len("clause"):].strip()
                                trimmed = trimmed.lstrip(":- _").strip()
                                if trimmed:
                                    candidates.append(trimmed)
                            elif identifier_lower.startswith("iso"):
                                trimmed = identifier_lower[len("iso"):].strip()
                                trimmed = trimmed.lstrip(":- _").strip()
                                if trimmed:
                                    candidates.append(trimmed)
                            candidates_to_expand = list(candidates)
                            for value in candidates_to_expand:
                                cleaned = value.replace("_", ".").replace(" ", "")
                                if cleaned and cleaned not in candidates:
                                    candidates.append(cleaned)
                                dotted = value.replace("_", ".")
                                if dotted and dotted not in candidates:
                                    candidates.append(dotted)
                            if next_item:
                                next_ids = {getattr(next_item, "item_id", None), getattr(next_item, "iso_reference", None)}
                                for candidate in candidates:
                                    if candidate in next_ids:
                                        resolved_item = next_item
                                        break
                            if not resolved_item:
                                for candidate in candidates:
                                    candidate = candidate.strip()
                                    if not candidate:
                                        continue
                                    lookup = None
                                    if "." in candidate and len(candidate) <= 32:
                                        iso_candidate = candidate.upper() if any(ch.isalpha() for ch in candidate) else candidate
                                        lookup = AuditDatabaseService.get_item_by_iso_reference(user_id, iso_candidate)
                                    if (not lookup or not lookup.success) and len(candidate) >= 8:
                                        lookup = AuditDatabaseService.get_item_by_item_id(user_id, candidate)
                                    if lookup and lookup.success and lookup.data:
                                        resolved_item = lookup.data
                                        break
                            if resolved_item:
                                call_args["item_id"] = resolved_item.item_id
                                call_args.pop("iso_reference", None)
                                next_item = resolved_item
                    if "user_id" not in call_args:
                        call_args["user_id"] = user_id
                    result = tool_registry[tool_name].invoke(call_args)
                except Exception as exc:  # noqa: BLE001
                    print(f"[AUDIT][ERROR] Tool {tool_name} raised {exc}")
                    result = {"success": False, "error": str(exc)}

                import json as _json

                if isinstance(result, dict):
                    print(f"[AUDIT] Tool result ({tool_name}): {result}")
                else:
                    print(f"[AUDIT] Tool raw result ({tool_name}): {str(result)[:500]}")

                parsed_result = None
                if isinstance(result, dict):
                    parsed_result = result
                elif isinstance(result, str):
                    try:
                        parsed_result = _json.loads(result)
                    except Exception as json_exc:  # noqa: BLE001
                        print(f"[AUDIT][WARN] Failed to decode tool result for {tool_name}: {json_exc}")
                        parsed_result = None

                if isinstance(parsed_result, dict):
                    data_block = parsed_result.get("data")
                    if tool_name == "get_audit_progress" and parsed_result.get("success") and data_block:
                        if isinstance(data_block, AuditProgress):
                            progress_data = data_block
                        else:
                            try:
                                progress_data = AuditProgress(**data_block)
                            except Exception:  # noqa: BLE001
                                pass
                    elif tool_name == "get_next_audit_item" and parsed_result.get("success"):
                        if data_block:
                            if isinstance(data_block, AuditItem):
                                next_item = data_block
                            else:
                                try:
                                    next_item = AuditItem(**data_block)
                                except Exception:  # noqa: BLE001
                                    pass
                        else:
                            next_item = None
                    elif tool_name == "list_audit_items" and parsed_result.get("success") and isinstance(data_block, dict):
                        progress_block = data_block.get("progress")
                        if progress_block:
                            if isinstance(progress_block, AuditProgress):
                                progress_data = progress_block
                            else:
                                try:
                                    progress_data = AuditProgress(**progress_block)
                                except Exception:  # noqa: BLE001
                                    pass

                    elif tool_name in {"skip_audit_item", "reset_audit_item", "delete_audit_item"} and parsed_result.get("success"):
                        refreshed_progress = AuditDatabaseService.get_progress_summary(user_id)
                        if refreshed_progress.success:
                            refreshed_data = refreshed_progress.data
                            if refreshed_data and not isinstance(refreshed_data, AuditProgress):
                                try:
                                    refreshed_data = AuditProgress(**refreshed_data)
                                except Exception:  # noqa: BLE001
                                    refreshed_data = None
                            if isinstance(refreshed_data, AuditProgress):
                                progress_data = refreshed_data
                        refreshed_item_result = AuditDatabaseService.get_next_actionable_item(user_id)
                        if refreshed_item_result.success:
                            refreshed_item = refreshed_item_result.data
                            if refreshed_item and not isinstance(refreshed_item, AuditItem):
                                try:
                                    refreshed_item = AuditItem(**refreshed_item)
                                except Exception:  # noqa: BLE001
                                    refreshed_item = None
                            next_item = refreshed_item

                payload = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False, default=str)
                if len(payload) > 8000:
                    payload = payload[:8000] + "..."

                messages.append(
                    ToolMessage(
                        content=payload,
                        tool_call_id=call.get("id"),
                        name=tool_name,
                    )
                )

                if isinstance(parsed_result, dict) and not parsed_result.get("success", True):
                    print(f"[AUDIT][WARN] Tool {tool_name} reported failure: {parsed_result}")

        final_text = ""
        requested_answer = False
        if final_ai and getattr(final_ai, "content", None):
            if isinstance(final_ai.content, list):
                final_text = " ".join(
                    part.content if hasattr(part, "content") else str(part)
                    for part in final_ai.content
                    if part
                )
            else:
                final_text = str(final_ai.content)

        if REQUEST_ANSWER_TOKEN in final_text:
            requested_answer = True
            final_text = final_text.replace(REQUEST_ANSWER_TOKEN, "").strip()

        if not final_text.strip():
            final_text = (
                "I'm ready to help you work through your ISO 27001 clauses. "
                "Let me know when you're ready to review the next item or need clarification."
            )

        fallback_needed = False
        if not requested_answer:
            if next_item and getattr(next_item, "status", "") != "answered":
                if state.get("awaiting_audit_answer", False) or "?" in final_text:
                    fallback_needed = True

        if fallback_needed:
            requested_answer = True

        if requested_answer and "submit clause answer" not in final_text.lower():
            final_text = final_text.rstrip()
            if final_text:
                final_text += "\n\nPlease use the \"Submit answer\" button below to record your response when you're ready."
            else:
                final_text = "Please use the \"Submit answer\" button below to record your response when you're ready."

        if phase_transition_note:
            note_lower = phase_transition_note.lower()
            if note_lower not in final_text.lower():
                final_text = (final_text.rstrip() + (("\n\n" if final_text.strip() else "") + phase_transition_note)).strip()

        if isinstance(progress_data, AuditProgress):
            clause_part = None
            if clause_total or clause_progress_dict.get("answered", 0) or clause_progress_dict.get("skipped", 0):
                clause_part = (
                    f"Clauses: {clause_progress_dict.get('answered', 0)} answered, "
                    f"{clause_progress_dict.get('pending', 0)} pending, "
                    f"{clause_progress_dict.get('skipped', 0)} skipped out of {clause_total}."
                )
            annex_part = None
            annex_excluded = annex_progress_dict.get("excluded", 0)
            if annex_total or annex_excluded or annex_progress_dict.get("skipped", 0) or annex_progress_dict.get("answered", 0):
                annex_part = (
                    f"Annexes: {annex_progress_dict.get('answered', 0)} answered, "
                    f"{annex_progress_dict.get('pending', 0)} pending, "
                    f"{annex_progress_dict.get('skipped', 0)} skipped out of {annex_total} active controls."
                )
                if annex_excluded:
                    annex_part = annex_part.rstrip(".") + f" ({annex_excluded} excluded)."
            summary_parts = [part for part in (clause_part, annex_part) if part]
            if summary_parts:
                progress_line = "Progress check - " + " ".join(summary_parts)
            else:
                progress_line = (
                    f"Progress check - {progress_data.answered} answered, "
                    f"{progress_data.pending} pending, {progress_data.skipped} skipped out of {progress_data.total}."
                )
            if progress_line.lower() not in final_text.lower():
                final_text = (final_text.rstrip() + (("\n\n" if final_text.strip() else "") + progress_line)).strip()

        progress_dict = progress_data.dict() if isinstance(progress_data, AuditProgress) else {}
        if not progress_dict:
            progress_dict = {
                "total": clause_total + annex_total,
                "pending": clause_progress_dict.get("pending", 0) + annex_progress_dict.get("pending", 0),
                "answered": clause_progress_dict.get("answered", 0) + annex_progress_dict.get("answered", 0),
                "skipped": clause_progress_dict.get("skipped", 0) + annex_progress_dict.get("skipped", 0),
            }
        next_item_dict = _item_to_context(next_item)

        assistant_actions = []
        if requested_answer and next_item_dict:
            assistant_actions.append({"type": "request_audit_answer", "item": next_item_dict})

        updated_risk_context = state.get("risk_context", {}) or {}
        updated_risk_context["audit"] = progress_dict
        updated_risk_context["audit_clauses"] = clause_progress_dict
        updated_risk_context["audit_annexes"] = annex_progress_dict
        updated_risk_context["audit_phase"] = audit_phase
        if phase_transition_note:
            updated_risk_context["audit_phase_note"] = phase_transition_note
        elif "audit_phase_note" in updated_risk_context:
            updated_risk_context.pop("audit_phase_note")

        if next_item_dict:
            next_item_dict["phase"] = audit_phase
            updated_risk_context["audit_next_item"] = next_item_dict
        elif "audit_next_item" in updated_risk_context:
            updated_risk_context.pop("audit_next_item")


        audit_context = {
            "phase": audit_phase,
            "next_item": next_item_dict,
            "last_updated": datetime.utcnow().isoformat(),
            "progress": progress_dict,
            "clauses": clause_progress_dict,
            "annexes": annex_progress_dict,
            "overall_progress_summary": overall_progress_summary,
            "clause_summary": clause_summary,
            "annex_summary": annex_summary,
        }
        if phase_transition_note:
            audit_context["phase_transition_note"] = phase_transition_note

        all_clauses_done = (clause_remaining == 0 and clause_progress_dict.get("total", 0) > 0) or clause_progress_dict.get("total", 0) == 0
        annex_total = annex_progress_dict.get("total", 0)
        all_annex_done = annex_total == 0 or annex_remaining == 0

        audit_complete = all_clauses_done and all_annex_done

        completion_note = ""
        if audit_complete:
            if annex_total == 0 and clause_progress_dict.get("total", 0) > 0:
                completion_note = (
                    "All clauses are complete and there are no Annex A controls assigned. Let me know when you want to move on to risk generation."
                )
            elif annex_total > 0 and annex_remaining == 0:
                completion_note = (
                    "All Annex A controls have been addressed. Let me know when you're ready to generate risks or review evidence."
                )

        if completion_note:
            if completion_note.lower() not in final_text.lower():
                final_text = (final_text.rstrip() + (("\n\n" if final_text.strip() else "") + completion_note)).strip()
            audit_context["completion_note"] = completion_note
            updated_risk_context["audit_completion_note"] = completion_note
        elif "audit_completion_note" in updated_risk_context:
            updated_risk_context.pop("audit_completion_note")

        if audit_complete:
            audit_context["all_completed"] = True
            updated_risk_context["audit_complete"] = True
        elif "audit_complete" in updated_risk_context:
            updated_risk_context.pop("audit_complete")

        updated_history = conversation_history + [{"user": user_input, "assistant": final_text}]

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
            "audit_phase": audit_phase,
            "assistant_actions": assistant_actions,
            "awaiting_audit_answer": requested_answer,
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
            "assistant_actions": [],
            "awaiting_audit_answer": False,
        }



