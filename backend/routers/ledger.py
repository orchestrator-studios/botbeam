"""Ledger routes — telemetry + record planes (The Ledger Book rev 19).

Additive namespace: nothing here touches devices, lockboxes, or memories.

Telemetry (sessions):
  POST /ledger/sessions/{sid}/signals     apply one lifecycle signal (the five hooks)
  POST /ledger/sessions/{sid}/events      DEPRECATED alias of /signals (pre-rev-19
                                          spelling; kept until the hooks flip, then removed)
  POST /ledger/sessions/{sid}/archive     dismiss a dormant session (409 if active)
  POST /ledger/sessions/{sid}/unarchive   restore one
  POST /ledger/sessions/archive           batch: by prefixes, or all dormant with a keep-list
  POST /ledger/sessions/sweep-report      one machine's transcript-presence observations
  GET  /ledger/sessions                   list; ?status= filters the stored column

Record (events + streams):
  POST /ledger/events                     log one event — atomic composite (invariant 9)
  GET  /ledger/events                     newest first; ?stream_id ?session_id ?since ?limit
  PUT  /ledger/streams/{sid}              create / field-replace a stream (409 closed)
  POST /ledger/streams/{sid}/close        close + log the closure event (one transaction)
  GET  /ledger/streams                    ?status=active|closed|all, staleness computed
  GET  /ledger/search                     ?q= across events and streams (recall's endpoint)

Views:
  GET  /ledger/index                      orientation markdown (SessionStart hook injects it)
  GET  /ledger/board                      the data structure the board view renders
  POST /ledger/admin/reset                test-only truncate (LEDGER_ADMIN_RESET)

Every mutation broadcasts {"event": "ledger_sessions"} to the owner's WS channel
so the board view refetches. Statuses are STORED (Book rev 17/18); the two-noun
rule (rev 19) holds: the telemetry plane says *signal*, the record plane says
*event* — hence the /signals rename, aliased during the hook cutover.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import get_async_db
from services.auth_service import get_current_user
from services.ledger_service import (
    LedgerService, LedgerError, NotFound, Conflict,
)
from websocket import manager

router = APIRouter()


class SessionSignal(BaseModel):
    """One hook signal. `signal` is the rev 19 field; `event` is the deprecated
    pre-rename spelling — exactly one must be present. `tool` accompanies
    PostToolUse only."""
    signal: Optional[str] = None
    event: Optional[str] = None
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


class CreateStream(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    working_paths: Optional[list[str]] = None


class StreamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Optional[str] = None
    state: Optional[str] = None
    next_action: Optional[str] = None
    open_loops: Optional[list[str]] = None
    working_paths: Optional[list[str]] = None


class LogEvent(BaseModel):
    """POST /ledger/events body. extra='forbid' also rejects the deferred
    `product` block with a 422, per the Book."""
    model_config = ConfigDict(extra="forbid")
    stream_id: str
    headline: str
    body: list[str]
    session_id: str
    stream_update: Optional[StreamUpdate] = None
    create_stream: Optional[CreateStream] = None


class StreamClose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = ""
    # Required (rev 19 ruling): the closure event is an event, and every event
    # has exactly one emitter — no exceptions.
    session_id: str


def _svc(db: AsyncSession) -> LedgerService:
    return LedgerService(db)


async def _notify(user_id: int) -> None:
    await manager.broadcast(user_id, {"event": "ledger_sessions"})


def _http(e: ValueError) -> HTTPException:
    """Map service exceptions to the Book's error convention."""
    if isinstance(e, Conflict):
        return HTTPException(status_code=409, detail={"error": "conflict", "reason": str(e)})
    if isinstance(e, NotFound):
        return HTTPException(status_code=404, detail={"error": "not_found", "reason": str(e)})
    return HTTPException(status_code=422, detail={"error": "validation", "reason": str(e)})


# ── record plane ─────────────────────────────────────────────────────────────

@router.post("/events", status_code=201)
async def log_event(
    body: LogEvent,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        out = await _svc(db).log_event(
            user.user_id,
            stream_id=body.stream_id, headline=body.headline, body=body.body,
            session_id=body.session_id,
            stream_update=body.stream_update.model_dump(exclude_unset=True) if body.stream_update else None,
            create_stream=body.create_stream.model_dump(exclude_unset=True) if body.create_stream else None,
        )
    except ValueError as e:
        await db.rollback()
        raise _http(e)
    await _notify(user.user_id)
    return out


@router.get("/events")
async def list_events(
    stream_id: Optional[str] = None, session_id: Optional[str] = None,
    since: Optional[datetime] = None, limit: int = 100,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    items = await _svc(db).events_list(
        user.user_id, stream_id=stream_id, session_id=session_id, since=since, limit=limit)
    return {"items": items, "next": None}


@router.put("/streams/{sid}")
async def put_stream(
    sid: str, body: StreamUpdate,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        # exclude_unset: absent fields are left alone; an explicit null clears.
        rep = await _svc(db).stream_put(user.user_id, sid, body.model_dump(exclude_unset=True))
    except ValueError as e:
        await db.rollback()
        raise _http(e)
    await _notify(user.user_id)
    return rep


@router.post("/streams/{sid}/close")
async def close_stream(
    sid: str, body: StreamClose,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        out = await _svc(db).stream_close(user.user_id, sid, body.reason, session_id=body.session_id)
    except ValueError as e:
        await db.rollback()
        raise _http(e)
    await _notify(user.user_id)
    return out


@router.get("/streams")
async def list_streams(
    status: str = "active",
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    items = await _svc(db).streams_list(user.user_id, status=status)
    return {"items": items, "next": None}


@router.get("/search")
async def search(
    q: str,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        items = await _svc(db).search(user.user_id, q)
    except LedgerError as e:
        raise _http(e)
    return {"items": items, "next": None}


@router.get("/index")
async def index(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    md = await _svc(db).index_md(user.user_id)
    return Response(content=md, media_type="text/markdown")


# ── telemetry plane ──────────────────────────────────────────────────────────

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


async def _apply_signal(sid: str, body: SessionSignal, user, db) -> dict:
    signal = body.signal or body.event
    if not signal:
        raise HTTPException(status_code=422, detail={
            "error": "validation", "field": "signal", "reason": "signal is required"})
    try:
        rep = await _svc(db).apply_event(
            user.user_id, sid, signal, cwd=body.cwd, machine=body.machine, tool=body.tool)
    except LedgerError as e:
        raise HTTPException(status_code=422, detail={"error": "validation", "field": "signal", "reason": str(e)})
    await _notify(user.user_id)
    return rep


@router.post("/sessions/{sid}/signals")
async def session_signal(
    sid: str, body: SessionSignal,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    return await _apply_signal(sid, body, user, db)


# Deprecated alias — the pre-rev-19 spelling the deployed hooks still post to.
# Removed in a later cleanup once every transmitter has flipped to /signals.
@router.post("/sessions/{sid}/events")
async def session_signal_legacy(
    sid: str, body: SessionSignal,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    return await _apply_signal(sid, body, user, db)


@router.post("/sessions/{sid}/archive")
async def archive_session(
    sid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        rep = await _svc(db).archive(user.user_id, sid)
    except ValueError as e:
        raise _http(e)
    await _notify(user.user_id)
    return rep


@router.post("/sessions/{sid}/unarchive")
async def unarchive_session(
    sid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        rep = await _svc(db).unarchive(user.user_id, sid)
    except ValueError as e:
        raise _http(e)
    await _notify(user.user_id)
    return rep


@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = None, machine: Optional[str] = None,
    relevant: Optional[bool] = None, stream_id: Optional[str] = None,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    items = await _svc(db).list(
        user.user_id, status=status, machine=machine, relevant=relevant, stream_id=stream_id)
    return {"items": items, "next": None}


# ── views ────────────────────────────────────────────────────────────────────

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
