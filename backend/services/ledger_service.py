"""Ledger sessions — the telemetry plane (The Ledger Book, phase 1).

Facts in, statuses out. This service owns both halves of the Book's session
contract: applying lifecycle signals to stored facts, and deriving status /
relevance from those facts on every read. One exception by decision (Ledger
Book rev 17): turn_state (waiting|processing) is STORED, declared by the
prompt/Stop signals rather than inferred — the sweep repairs a crashed
session's stale 'processing' as an explicit write.

Derivation cascade (the Book's session cheat sheet, first stop wins):
  never prompted → not relevant (hidden) · archived (no event since) → hidden ·
  expired (transcript missing xN sweeps, no event since) → hidden ·
  dormant (ended, or silent past the silence window) → gray ·
  active: activity = turn_state, plus run while last_run_at is within the
  run window.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from models import LedgerSession

logger = logging.getLogger("botbeam.ledger")

# Lifecycle signals the hooks may send — a closed set (422 otherwise).
SIGNALS = {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd", "PostToolUse"}

# Run-vs-read classification is service policy, per the Book: hooks transmit
# every tool completion unclassified; only these refresh last_run_at.
MUTATING_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"}


class LedgerError(ValueError):
    """Invalid ledger request — surfaced as a 422."""


class SessionActive(ValueError):
    """Archive refused because the session is active — surfaced as a 409."""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _label(cwd: Optional[str], sid: str) -> Optional[str]:
    if not cwd:
        return None
    base = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or cwd
    return f"{base}·{sid[:6]}"


class LedgerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── derivation ────────────────────────────────────────────────────────────

    @staticmethod
    def derive(s: LedgerSession, now: Optional[datetime] = None) -> dict:
        """Pure facts → {status, activity, relevant}. Never touches the DB."""
        now = now or datetime.utcnow()
        silence = timedelta(minutes=settings.LEDGER_SILENCE_WINDOW_MINUTES)
        run_window = timedelta(seconds=settings.LEDGER_RUN_WINDOW_SECONDS)

        # "No event since X" is expressed as last_event_at <= X: every signal
        # (including the one that sets X) bumps last_event_at, so a strictly
        # later heartbeat means life after X.
        archived = s.archived_at is not None and s.last_event_at <= s.archived_at
        expired = (
            s.sweep_miss_count >= settings.LEDGER_EXPIRY_SWEEP_MISSES
            and s.transcript_missing_since is not None
            and s.last_event_at <= s.transcript_missing_since
        )
        ended = s.ended_at is not None and s.last_event_at <= s.ended_at
        silent = (now - s.last_event_at) > silence

        if archived:
            status, activity = "archived", None
        elif expired:
            status, activity = "expired", None
        elif ended or silent:
            status, activity = "dormant", None
        else:
            # Activity IS the stored turn_state — declared by prompt/Stop
            # signals, never inferred (Ledger Book rev 17). Run adds the bolt
            # while the last mutation is inside the run window.
            status = "active"
            if s.turn_state == "processing":
                in_run = s.last_run_at is not None and (now - s.last_run_at) <= run_window
                activity = "run" if in_run else "processing"
            else:
                activity = "waiting"

        relevant = bool(s.ever_prompted) and status not in ("archived", "expired")
        return {"status": status, "activity": activity, "relevant": relevant}

    def _repr(self, s: LedgerSession, now: Optional[datetime] = None) -> dict:
        """The Session wire representation: stored facts + derived fields."""
        d = self.derive(s, now)
        return {
            "id": s.id,
            "workspace_id": s.workspace_id,
            "machine": s.machine,
            "label": s.label,
            "turn_state": s.turn_state,
            "first_seen": _iso(s.first_seen),
            "last_event_at": _iso(s.last_event_at),
            "last_prompt_at": _iso(s.last_prompt_at),
            "last_stop_at": _iso(s.last_stop_at),
            "last_run_at": _iso(s.last_run_at),
            "ended_at": _iso(s.ended_at),
            "ever_prompted": bool(s.ever_prompted),
            "archived_at": _iso(s.archived_at),
            "transcript_missing_since": _iso(s.transcript_missing_since),
            **d,
        }

    # ── signals ──────────────────────────────────────────────────────────────

    async def apply_event(
        self, user_id: int, sid: str, event: str,
        cwd: Optional[str] = None, machine: Optional[str] = None,
        tool: Optional[dict] = None,
    ) -> dict:
        if event not in SIGNALS:
            raise LedgerError(f'Unknown event "{event}". Must be one of: {", ".join(sorted(SIGNALS))}')
        now = datetime.utcnow()
        s = await self.db.get(LedgerSession, sid)
        if s is None:
            s = LedgerSession(id=sid, user_id=user_id, first_seen=now)
            self.db.add(s)
        elif s.user_id != user_id:
            raise LedgerError("Session belongs to another user")

        # Identity fields settle on first sight and refresh harmlessly after.
        if cwd:
            s.workspace_id = cwd
            s.label = _label(cwd, sid)
        if machine:
            s.machine = machine

        # Any signal is a sign of life: heartbeat + expiry facts self-correct.
        s.last_event_at = now
        s.transcript_missing_since = None
        s.sweep_miss_count = 0

        if event == "UserPromptSubmit":
            s.turn_state = "processing"
            s.last_prompt_at = now
            s.ever_prompted = True
        elif event == "Stop":
            s.turn_state = "waiting"
            s.last_stop_at = now
        elif event == "SessionEnd":
            s.turn_state = "waiting"
            s.ended_at = now
        elif event == "PostToolUse":
            name = (tool or {}).get("name")
            if name in MUTATING_TOOLS:
                s.last_run_at = now

        await self.db.commit()
        await self.db.refresh(s)
        logger.debug("ledger event %s (session=%s, user=%s)", event, sid[:6], user_id)
        return self._repr(s, now)

    # ── archive / unarchive ──────────────────────────────────────────────────

    async def archive(self, user_id: int, sid: str) -> dict:
        s = await self._own(user_id, sid)
        if self.derive(s)["status"] == "active":
            raise SessionActive("session is active")
        s.archived_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(s)
        logger.info("ledger archive (session=%s, user=%s)", sid[:6], user_id)
        return self._repr(s)

    async def unarchive(self, user_id: int, sid: str) -> dict:
        s = await self._own(user_id, sid)
        s.archived_at = None
        await self.db.commit()
        await self.db.refresh(s)
        return self._repr(s)

    async def archive_batch(
        self, user_id: int,
        prefixes: Optional[list[str]] = None,
        all_: bool = False, keep: Optional[list[str]] = None,
    ) -> list[dict]:
        """Archive by id prefix, or everything dormant with a keep-list.

        Active sessions are silently skipped in batch form — the point is
        clearing the board, and the board's active cards are never clutter.
        """
        rows = (await self.db.execute(
            select(LedgerSession).where(LedgerSession.user_id == user_id)
        )).scalars().all()
        keep = keep or []
        now = datetime.utcnow()
        out = []
        for s in rows:
            if any(s.id.startswith(k) for k in keep):
                continue
            if not all_ and not any(s.id.startswith(p) for p in (prefixes or [])):
                continue
            d = self.derive(s, now)
            if d["status"] == "active" or s.archived_at is not None and not d["relevant"]:
                continue
            s.archived_at = now
            out.append(s)
        await self.db.commit()
        logger.info("ledger batch archive (%d sessions, user=%s)", len(out), user_id)
        return [self._repr(s, now) for s in out]

    # ── sweep ────────────────────────────────────────────────────────────────

    async def sweep_report(self, user_id: int, machine: str, observed: list[dict]) -> int:
        """One machine's transcript-presence observations. Returns rows changed."""
        now = datetime.utcnow()
        applied = 0
        for o in observed:
            sid = o.get("session_id")
            if not sid:
                continue
            s = await self.db.get(LedgerSession, sid)
            if s is None or s.user_id != user_id or (s.machine and machine and s.machine != machine):
                continue
            if o.get("transcript_present"):
                if s.transcript_missing_since is not None or s.sweep_miss_count:
                    s.transcript_missing_since = None
                    s.sweep_miss_count = 0
                    applied += 1
            else:
                if s.transcript_missing_since is None:
                    s.transcript_missing_since = now
                s.sweep_miss_count += 1
                applied += 1
            # Crashed-session cleanup: a dormant row stuck at 'processing'
            # (killed mid-turn, so no Stop ever arrived) is repaired here —
            # an explicit write, not an inference at read time.
            if s.turn_state == "processing" and self.derive(s, now)["status"] == "dormant":
                s.turn_state = "waiting"
                applied += 1
        await self.db.commit()
        return applied

    # ── reads ────────────────────────────────────────────────────────────────

    async def list(
        self, user_id: int,
        status: Optional[str] = None, machine: Optional[str] = None,
        relevant: Optional[bool] = None,
    ) -> list[dict]:
        q = select(LedgerSession).where(LedgerSession.user_id == user_id)
        if machine:
            q = q.where(LedgerSession.machine == machine)
        rows = (await self.db.execute(q)).scalars().all()
        now = datetime.utcnow()
        out = [self._repr(s, now) for s in rows]
        if status:
            out = [r for r in out if r["status"] == status]
        if relevant is not None:
            out = [r for r in out if r["relevant"] == relevant]
        out.sort(key=lambda r: r["last_event_at"] or "", reverse=True)
        return out

    async def board(self, user_id: int) -> dict:
        """The data structure the BotBeam board view is built from.

        Sessions: relevant only, active first (run/processing, then waiting),
        then dormant by recency. Events and products ship empty in phase 1 —
        the record plane lands in phase 2.
        """
        now = datetime.utcnow()
        sessions = await self.list(user_id, relevant=True)
        # Stable two-pass sort: recency within each band, bands ordered
        # run/processing → waiting → dormant.
        rank = {"run": 0, "processing": 0, "waiting": 1}
        sessions.sort(key=lambda r: r["last_event_at"] or "", reverse=True)
        sessions.sort(key=lambda r: (0 if r["status"] == "active" else 1, rank.get(r["activity"], 2)))
        return {"sessions": sessions, "events": [], "products": [], "as_of": _iso(now)}

    # ── test support ─────────────────────────────────────────────────────────

    async def reset(self, user_id: int) -> int:
        """Truncate the caller's ledger rows. Test-only (LEDGER_ADMIN_RESET)."""
        res = await self.db.execute(delete(LedgerSession).where(LedgerSession.user_id == user_id))
        await self.db.commit()
        logger.info("ledger reset (%s sessions, user=%s)", res.rowcount, user_id)
        return res.rowcount or 0

    # ── internals ────────────────────────────────────────────────────────────

    async def _own(self, user_id: int, sid: str) -> LedgerSession:
        s = await self.db.get(LedgerSession, sid)
        if s is None or s.user_id != user_id:
            raise LedgerError("Session not found")
        return s
