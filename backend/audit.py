from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from auth import get_current_user
from database import (
    AuditDatabaseService,
    S3EvidenceStorage,
    AUDIT_EVIDENCE_MAX_BYTES,
    AUDIT_EVIDENCE_BUCKET,
)
from models import AuditItem, AuditItemsResponse, AuditItemResponse, AuditProgressResponse, AuditProgress


router = APIRouter(prefix="/audit", tags=["audit"])


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

