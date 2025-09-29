import asyncio
import threading
from typing import Any, Dict, Optional

from langchain_core.tools import tool

from database import AuditDatabaseService
from models import AuditItem, AuditProgress, AuditTypeProgress, AuditPhaseProgress


def _serialize_data(data: Any):
    if isinstance(data, AuditItem):
        return data.dict()
    if isinstance(data, (AuditProgress, AuditTypeProgress, AuditPhaseProgress)):
        return data.dict()
    if isinstance(data, list):
        return [_serialize_data(item) for item in data]
    if isinstance(data, dict):
        return {key: _serialize_data(value) for key, value in data.items()}
    return data


def _result_to_dict(result) -> Dict[str, Any]:
    if result is None:
        return {"success": False, "message": "No result returned"}

    return {
        "success": bool(result.success),
        "message": result.message,
        "data": _serialize_data(result.data),
    }



def _run_coroutine_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Dict[str, Any] = {}
    error: Dict[str, Exception] = {}

    def _worker():
        try:
            result["data"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            error["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    if "error" in error:
        raise error["error"]
    return result.get("data")

@tool("get_audit_progress")
def get_audit_progress(user_id: str) -> Dict[str, Any]:
    """Fetch user's audit clause progress counts."""
    result = AuditDatabaseService.get_progress_summary(user_id)
    return _result_to_dict(result)


@tool("get_next_audit_item")
def get_next_audit_item(user_id: str) -> Dict[str, Any]:
    """Fetch the next pending or skipped audit clause for the user."""
    result = AuditDatabaseService.get_next_actionable_item(user_id)
    return _result_to_dict(result)


@tool("get_annex_progress")
def get_annex_progress(user_id: str) -> Dict[str, Any]:
    """Fetch clause and annex progress details."""
    result = AuditDatabaseService.get_phase_progress(user_id)
    return _result_to_dict(result)


@tool("get_next_annex_item")
def get_next_annex_item(user_id: str) -> Dict[str, Any]:
    """Fetch the next pending or skipped annex control for the user."""
    result = AuditDatabaseService.get_next_item_by_type(user_id, "annex")
    return _result_to_dict(result)


@tool("exclude_annex_item")
def exclude_annex_item(user_id: str, item_id: str) -> Dict[str, Any]:
    """Exclude a specific annex control from the assessment."""
    result = _run_coroutine_sync(AuditDatabaseService.exclude_annex_item(user_id, item_id))
    return _result_to_dict(result)


@tool("reinstate_annex_item")
def reinstate_annex_item(user_id: str, item_id: str) -> Dict[str, Any]:
    """Reinstate a previously excluded annex control."""
    result = _run_coroutine_sync(AuditDatabaseService.reinstate_annex_item(user_id, item_id))
    return _result_to_dict(result)


@tool("exclude_annex_group")
def exclude_annex_group(user_id: str, annex_group: str) -> Dict[str, Any]:
    """Exclude an entire annex group (e.g., A.5) from the assessment."""
    result = _run_coroutine_sync(AuditDatabaseService.exclude_annex_group(user_id, annex_group))
    return _result_to_dict(result)


@tool("reinstate_annex_group")
def reinstate_annex_group(user_id: str, annex_group: str) -> Dict[str, Any]:
    """Reinstate an annex group that was previously excluded."""
    result = _run_coroutine_sync(AuditDatabaseService.reinstate_annex_group(user_id, annex_group))
    return _result_to_dict(result)


@tool("skip_annex_group")
def skip_annex_group(user_id: str, annex_group: str) -> Dict[str, Any]:
    """Mark all controls within an annex group as skipped."""
    result = _run_coroutine_sync(AuditDatabaseService.mark_annex_group_skipped(user_id, annex_group))
    return _result_to_dict(result)


@tool("reset_annex_group")
def reset_annex_group(user_id: str, annex_group: str) -> Dict[str, Any]:
    """Reset all controls within an annex group back to pending."""
    result = _run_coroutine_sync(AuditDatabaseService.reset_annex_group_to_pending(user_id, annex_group))
    return _result_to_dict(result)


@tool("list_audit_items")
def list_audit_items(user_id: str, status: Optional[str] = None, limit: int = 50, skip: int = 0) -> Dict[str, Any]:
    """List audit items for the user with optional status filter."""
    result = _run_coroutine_sync(AuditDatabaseService.get_audit_items(user_id, status=status, limit=limit, skip=skip))
    return _result_to_dict(result)




@tool("skip_audit_item")
def skip_audit_item(user_id: str, item_id: str) -> Dict[str, Any]:
    """Mark a clause as skipped for now."""
    result = _run_coroutine_sync(AuditDatabaseService.mark_skipped(user_id, item_id))
    return _result_to_dict(result)


@tool("reset_audit_item")
def reset_audit_item(user_id: str, item_id: str) -> Dict[str, Any]:
    """Reset a clause back to pending status."""
    result = _run_coroutine_sync(AuditDatabaseService.reset_to_pending(user_id, item_id))
    return _result_to_dict(result)


@tool("delete_audit_item")
def delete_audit_item(user_id: str, item_id: str) -> Dict[str, Any]:
    """Remove a clause from the user's audit assessment."""
    result = _run_coroutine_sync(AuditDatabaseService.delete_item(user_id, item_id))
    return _result_to_dict(result)

