"""Ledger routes — the sessions plane (The Ledger Book, phase 1).

Additive namespace: nothing here touches devices, lockboxes, or memories.
  POST /ledger/sessions/{sid}/events      apply one lifecycle signal (the five hooks)
  POST /ledger/sessions/{sid}/archive     dismiss a dormant session (409 if active)
  POST /ledger/sessions/{sid}/unarchive   restore one
  POST /ledger/sessions/archive           batch: by prefixes, or all dormant with a keep-list
  POST /ledger/sessions/sweep-report      one machine's transcript-presence observations
  GET  /ledger/sessions                   list; ?status= filters the stored column
  GET  /ledger/board                      the data structure the board view renders
  POST /ledger/admin/reset                test-only truncate (LEDGER_ADMIN_RESET)

Every mutation broadcasts {"event": "ledger_sessions"} to the owner's WS channel
so the board view refetches. Both statuses are STORED by decision — turn_state
(waiting|processing, Book rev 17) and the lifecycle status (active|dormant|
archived|expired, Book rev 18); ?status= filters on the stored column. Only
display fields (activity, relevant) are computed per read.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import get_async_db
from services.auth_service import get_current_user
from services.ledger_service import LedgerService, LedgerError, SessionActive
from websocket import manager

router = APIRouter()


class SessionSignal(BaseModel):
    """One hook signal. `tool` accompanies PostToolUse only."""
    event: str
    cwd: Optional[str] = None
    machine: Optional[str] = None
    tool: Optional[dict] = None


class BatchArchive(BaseModel):
    prefixes: Optional[list[str]] = None
    all: bool = False
    keep: Optional[list[str]] = None


class SweepObservation(BaseModel):
    session_id: str
    transcript_present: bool


class SweepReport(BaseModel):
    machine: str
    observed: list[SweepObservation]


def _svc(db: AsyncSession) -> LedgerService:
    return LedgerService(db)


async def _notify(user_id: int) -> None:
    await manager.broadcast(user_id, {"event": "ledger_sessions"})


@router.post("/sessions/sweep-report")
async def sweep_report(
    body: SweepReport,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    applied = await _svc(db).sweep_report(
        user.user_id, body.machine, [o.model_dump() for o in body.observed])
    if applied:
        await _notify(user.user_id)
    return {"applied": applied}


@router.post("/sessions/archive")
async def archive_batch(
    body: BatchArchive,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    if not body.all and not body.prefixes:
        raise HTTPException(status_code=422, detail={
            "error": "validation", "field": "prefixes",
            "reason": "give prefixes, or all=true (optionally with keep)"})
    items = await _svc(db).archive_batch(
        user.user_id, prefixes=body.prefixes, all_=body.all, keep=body.keep)
    await _notify(user.user_id)
    return {"items": items}


@router.post("/sessions/{sid}/events")
async def session_event(
    sid: str, body: SessionSignal,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        rep = await _svc(db).apply_event(
            user.user_id, sid, body.event, cwd=body.cwd, machine=body.machine, tool=body.tool)
    except LedgerError as e:
        raise HTTPException(status_code=422, detail={"error": "validation", "field": "event", "reason": str(e)})
    await _notify(user.user_id)
    return rep


@router.post("/sessions/{sid}/archive")
async def archive_session(
    sid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        rep = await _svc(db).archive(user.user_id, sid)
    except SessionActive:
        raise HTTPException(status_code=409, detail={"error": "conflict", "reason": "session is active"})
    except LedgerError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": str(e)})
    await _notify(user.user_id)
    return rep


@router.post("/sessions/{sid}/unarchive")
async def unarchive_session(
    sid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        rep = await _svc(db).unarchive(user.user_id, sid)
    except LedgerError as e:
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": str(e)})
    await _notify(user.user_id)
    return rep


@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = None, machine: Optional[str] = None,
    relevant: Optional[bool] = None,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    items = await _svc(db).list(user.user_id, status=status, machine=machine, relevant=relevant)
    return {"items": items, "next": None}


@router.get("/board")
async def board(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await _svc(db).board(user.user_id)


@router.post("/admin/reset")
async def admin_reset(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    if not settings.LEDGER_ADMIN_RESET:
        raise HTTPException(status_code=403, detail={"error": "forbidden", "reason": "LEDGER_ADMIN_RESET is off"})
    n = await _svc(db).reset(user.user_id)
    await _notify(user.user_id)
    return {"deleted_sessions": n}
