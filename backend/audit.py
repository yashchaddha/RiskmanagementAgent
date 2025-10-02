from __future__ import annotations

import os
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from auth import get_current_user
from database import (
    AuditDatabaseService,
    S3EvidenceStorage,
    AUDIT_EVIDENCE_MAX_BYTES,
    AUDIT_EVIDENCE_BUCKET,
)
from dependencies import get_llm
from prompt_utils import load_prompt

from langchain_core.messages import SystemMessage, HumanMessage

from models import AuditItem, AuditItemsResponse, AuditItemResponse, AuditProgressResponse, AuditProgress, AuditEvidence


router = APIRouter(prefix="/audit", tags=["audit"])

VALIDATION_PREVIEW_MAX_BYTES = int(os.getenv("AUDIT_VALIDATION_PREVIEW_MAX_BYTES", str(512 * 1024)))
VALIDATION_PREVIEW_MAX_CHARS = int(os.getenv("AUDIT_VALIDATION_PREVIEW_MAX_CHARS", "4000"))
VALIDATION_SUMMARY_MAX_CHARS = int(os.getenv("AUDIT_VALIDATION_SUMMARY_MAX_CHARS", "1200"))
JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _truncate_text(value: Optional[str], limit: int) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _extract_json_payload(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    match = JSON_BLOCK_PATTERN.search(content)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    normalized = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "fully_compliant": "compliant",
        "compliant": "compliant",
        "full_compliance": "compliant",
        "partial": "partially_compliant",
        "partially_compliant": "partially_compliant",
        "partial_compliance": "partially_compliant",
        "non_compliant": "not_compliant",
        "noncompliant": "not_compliant",
        "not_compliant": "not_compliant",
        "non_compliance": "not_compliant",
        "not_applicable": "not_relevant",
        "not_relevant": "not_relevant",
        "excluded": "not_relevant",
        "inconclusive": "inconclusive",
        "insufficient": "inconclusive",
    }
    return mapping.get(normalized, normalized)


def _coerce_confidence(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    number = max(0.0, min(1.0, number))
    return round(number, 3)


def _coerce_recommendations(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return [stripped]
    return []


def _prepare_text_preview(data: bytes, content_type: Optional[str], *, max_chars: int) -> tuple[str, bool]:
    if not data:
        return "", False

    decoded: Optional[str] = None
    if content_type and content_type.startswith("text"):
        decoded = data.decode("utf-8", errors="ignore")
    elif content_type in {"application/json", "application/xml", "application/xhtml+xml", "application/yaml", "application/x-yaml"}:
        decoded = data.decode("utf-8", errors="ignore")
    else:
        fallback = data.decode("utf-8", errors="ignore")
        if fallback.strip():
            decoded = fallback

    if not decoded:
        return "", False

    normalized = decoded.replace("\ufeff", "").strip()
    if not normalized:
        return "", False

    preview = normalized[:max_chars]
    truncated = len(normalized) > max_chars
    return preview, truncated



class AnswerRequest(BaseModel):
    answer: str


class SimpleResponse(BaseModel):
    success: bool
    message: str


def _ensure_user_id(user: dict) -> str:
    user_id = user.get("username") if user else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user not found")
    return user_id


@router.get("/items", response_model=AuditItemsResponse)
async def list_audit_items(
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    current_user=Depends(get_current_user),
):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.get_audit_items(user_id, status=status, limit=limit, skip=skip)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    payload = result.data or {}
    items = payload.get("items", [])
    progress = payload.get("progress")

    if progress and not isinstance(progress, AuditProgress):
        progress = AuditProgress(**progress)

    normalized_items = [item if isinstance(item, AuditItem) else AuditItem(**item) for item in items]

    return AuditItemsResponse(
        success=True,
        message="Audit items fetched successfully",
        data=normalized_items,
        progress=progress,
    )


@router.get("/items/{item_id}", response_model=AuditItemResponse)
async def get_audit_item(item_id: str, current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.get_item(user_id, item_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)


@router.get("/next", response_model=AuditItemResponse)
async def get_next_audit_item(current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = AuditDatabaseService.get_next_actionable_item(user_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(
        success=True,
        message=result.message,
        data=item,
    )


@router.get("/progress", response_model=AuditProgressResponse)
async def get_audit_progress(current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = AuditDatabaseService.get_progress_summary(user_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    progress = result.data
    if progress and not isinstance(progress, AuditProgress):
        progress = AuditProgress(**progress)

    return AuditProgressResponse(success=True, message=result.message, data=progress)


@router.post("/items/{item_id}/answer", response_model=AuditItemResponse)
async def submit_audit_answer(
    item_id: str,
    request: AnswerRequest,
    current_user=Depends(get_current_user),
):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.submit_answer(user_id, item_id, request.answer)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)


@router.post("/items/{item_id}/skip", response_model=AuditItemResponse)
async def skip_audit_item(item_id: str, current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.mark_skipped(user_id, item_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)


@router.post("/items/{item_id}/reset", response_model=AuditItemResponse)
async def reset_audit_item(item_id: str, current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.reset_to_pending(user_id, item_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)


@router.delete("/items/{item_id}", response_model=SimpleResponse)
async def delete_audit_item(item_id: str, current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.delete_item(user_id, item_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return SimpleResponse(success=True, message=result.message)


@router.post("/items/{item_id}/evidence", response_model=AuditItemResponse)
async def upload_audit_evidence(
    item_id: str,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    checksum: Optional[str] = Form(default=None),
):
    if not AUDIT_EVIDENCE_BUCKET:
        raise HTTPException(status_code=500, detail="Audit evidence storage is not configured")

    user_id = _ensure_user_id(current_user)

    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > AUDIT_EVIDENCE_MAX_BYTES:
        max_mb = AUDIT_EVIDENCE_MAX_BYTES // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"Evidence file exceeds maximum size of {max_mb} MB")

    try:
        object_key, version_id = S3EvidenceStorage.upload_fileobj(
            file.file,
            user_id=user_id,
            item_id=item_id,
            filename=file.filename or "evidence",
            content_type=file.content_type,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    result = await AuditDatabaseService.append_evidence(
        user_id,
        item_id,
        file_name=file.filename or "evidence",
        file_size=file_size,
        content_type=file.content_type,
        object_key=object_key,
        uploaded_by=user_id,
        checksum=checksum,
        version_id=version_id,
    )

    if not result.success:
        # Attempt to clean up uploaded object if metadata storage failed
        try:
            S3EvidenceStorage.delete_object(object_key)
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)



@router.post("/items/{item_id}/evidence/{evidence_id}/validate", response_model=AuditItemResponse)
async def validate_audit_evidence(
    item_id: str,
    evidence_id: str,
    current_user=Depends(get_current_user),
):
    user_id = _ensure_user_id(current_user)

    lookup = await AuditDatabaseService.get_audit_evidence(user_id, item_id, evidence_id)
    if not lookup.success:
        raise HTTPException(status_code=404, detail=lookup.message)

    payload = lookup.data or {}
    item = payload.get("item")
    evidence = payload.get("evidence")

    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)
    if evidence and not isinstance(evidence, AuditEvidence):
        evidence = AuditEvidence(**evidence)

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence record not found")

    bucket_name = evidence.bucket or AUDIT_EVIDENCE_BUCKET
    if not bucket_name:
        raise HTTPException(status_code=500, detail="Audit evidence storage is not configured")
    try:
        raw_bytes, truncated, download_content_type = S3EvidenceStorage.download_object(
            evidence.object_key,
            bucket=bucket_name,
            max_bytes=VALIDATION_PREVIEW_MAX_BYTES,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to download evidence: {exc}") from exc

    preview_text, preview_text_truncated = _prepare_text_preview(
        raw_bytes,
        evidence.content_type or download_content_type,
        max_chars=VALIDATION_PREVIEW_MAX_CHARS,
    )
    preview_truncated = truncated or preview_text_truncated

    answer_text = _truncate_text(getattr(item, "answer", None), 1200)
    description_text = _truncate_text(getattr(item, "description", None), 1500)
    evidence_preview = preview_text or "[No textual content could be extracted from this file.]"

    human_prompt = (
        "Evaluate whether the provided evidence supports the ISO/IEC 27001 clause or annex control.\n"
        "Clause/control details:\n"
        f"- Type: {getattr(item, 'type', 'unknown')}\n"
        f"- ISO reference: {getattr(item, 'iso_reference', '')}\n"
        f"- Title: {getattr(item, 'title', '') or 'Not provided'}\n"
        f"- Description: {description_text or 'Not provided'}\n"
        f"- User response: {answer_text or 'Not provided'}\n\n"
        "Evidence metadata:\n"
        f"- File name: {evidence.file_name}\n"
        f"- Content type: {evidence.content_type or download_content_type or 'Unknown'}\n"
        f"- File size (bytes): {evidence.file_size}\n"
        f"- Preview truncated: {'yes' if preview_truncated else 'no'}\n\n"
        "Evidence content preview (truncated for the model if necessary):\n"
        f"{evidence_preview}\n"
    )

    llm = get_llm()
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", None)
    system_prompt = load_prompt("audit_evidence_validation_system.txt")

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]

    llm_payload: Optional[Dict[str, Any]] = None
    raw_response = ""
    llm_error: Optional[str] = None

    try:
        completion = await llm.ainvoke(messages)
        raw_response = getattr(completion, "content", "") or ""
        llm_payload = _extract_json_payload(raw_response)
        if not llm_payload:
            llm_error = "LLM response could not be parsed into JSON."
    except Exception as exc:  # noqa: BLE001
        llm_error = f"LLM call failed: {exc}"

    recommendations = _coerce_recommendations(llm_payload.get("recommendations")) if llm_payload else []
    status_value = _normalize_status(llm_payload.get("status")) if llm_payload else "inconclusive"
    confidence_value = _coerce_confidence(llm_payload.get("confidence")) if llm_payload else None

    summary_text: Optional[str] = None
    if llm_payload and llm_payload.get("summary"):
        summary_text = _truncate_text(str(llm_payload.get("summary")), VALIDATION_SUMMARY_MAX_CHARS)
    elif raw_response:
        summary_text = _truncate_text(raw_response, VALIDATION_SUMMARY_MAX_CHARS)
    elif llm_error:
        summary_text = llm_error

    validation_timestamp = datetime.utcnow()
    validation_fields = {
        "validation_status": status_value,
        "validation_summary": summary_text,
        "validation_confidence": confidence_value,
        "validation_recommendations": recommendations,
        "last_validated_at": validation_timestamp,
        "validation_model": model_name,
        "validation_error": llm_error,
        "validation_truncated": preview_truncated,
    }

    record_result = await AuditDatabaseService.record_evidence_validation(
        user_id,
        item_id,
        evidence_id,
        validation_fields=validation_fields,
    )
    if not record_result.success:
        raise HTTPException(status_code=500, detail=record_result.message)

    result_payload = record_result.data or {}
    updated_item = result_payload.get("item")
    if updated_item and not isinstance(updated_item, AuditItem):
        updated_item = AuditItem(**updated_item)

    message_text = summary_text or (llm_error or "Evidence validation updated.")
    success_flag = llm_payload is not None

    return AuditItemResponse(success=success_flag, message=message_text, data=updated_item)

@router.delete("/items/{item_id}/evidence/{evidence_id}", response_model=AuditItemResponse)
async def delete_audit_evidence(item_id: str, evidence_id: str, current_user=Depends(get_current_user)):
    user_id = _ensure_user_id(current_user)
    result = await AuditDatabaseService.remove_evidence(user_id, item_id, evidence_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    item = result.data
    if item and not isinstance(item, AuditItem):
        item = AuditItem(**item)

    return AuditItemResponse(success=True, message=result.message, data=item)
