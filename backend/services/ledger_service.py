"""Ledger sessions — the telemetry plane (The Ledger Book, phase 1).

Facts and statuses in, statuses out. Both session statuses are STORED, written
by exactly one writer per transition (Ledger Book rev 17 + 18) — nothing
lifecycle is derived at read time:

  turn_state (waiting|processing) — UserPromptSubmit → processing, Stop /
  SessionEnd → waiting (rev 17). The sweep repairs a stale 'processing' on a
  non-active row as an explicit write.

  status (active|dormant|archived|expired) — every hook signal except
  SessionEnd → active (this is what un-archives and un-expires); SessionEnd →
  dormant; POST /archive → archived (409 while active); POST /unarchive →
  dormant; the sweep → expired at N consecutive transcript misses (rev 18).
  A crashed session keeps status='active' — an accepted known gap until a
  sweep-repair mechanism lands; deliberately no inference papers over it.

What remains computed per read are display windows and filters only:
  activity — the glyph for active sessions: turn_state, upgraded to 'run'
  while the last mutation is inside the run window.
  relevant — ever_prompted and not archived/expired (the board filter).
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

    # ── computed display fields (windows/filters only — never lifecycle) ─────

    @staticmethod
    def activity(s: LedgerSession, now: Optional[datetime] = None) -> Optional[str]:
        """Active sessions' glyph: stored turn_state, plus the run bolt while
        the last mutation is inside the run window. None off the active band."""
        if s.status != "active":
            return None
        if s.turn_state == "processing":
            now = now or datetime.utcnow()
            run_window = timedelta(seconds=settings.LEDGER_RUN_WINDOW_SECONDS)
            in_run = s.last_run_at is not None and (now - s.last_run_at) <= run_window
            return "run" if in_run else "processing"
        return "waiting"

    def _repr(self, s: LedgerSession, now: Optional[datetime] = None) -> dict:
        """The Session wire representation: stored facts + computed display fields."""
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
            "status": s.status,
            "activity": self.activity(s, now),
            "relevant": bool(s.ever_prompted) and s.status not in ("archived", "expired"),
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

        # Universal writes: heartbeat, expiry-fact resets, and the status.
        # Every signal but SessionEnd declares the session active — this is the
        # explicit un-archive / un-expire (rev 18), not a derivation.
        s.last_event_at = now
        s.transcript_missing_since = None
        s.sweep_miss_count = 0
        if event == "SessionEnd":
            s.status = "dormant"
        else:
            if s.status == "archived":
                s.archived_at = None
            s.status = "active"

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
        if s.status == "active":
            raise SessionActive("session is active")
        s.status = "archived"
        s.archived_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(s)
        logger.info("ledger archive (session=%s, user=%s)", sid[:6], user_id)
        return self._repr(s)

    async def unarchive(self, user_id: int, sid: str) -> dict:
        s = await self._own(user_id, sid)
        s.status = "dormant"
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
        Already-archived rows are skipped too (idempotent by inspection).
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
            if s.status in ("active", "archived"):
                continue
            s.status = "archived"
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
                # The sweep is the one writer of 'expired' (rev 18). "No event
                # since" is structural: any signal zeroes the miss count, so
                # reaching the threshold means the session never spoke again.
                if s.sweep_miss_count >= settings.LEDGER_EXPIRY_SWEEP_MISSES:
                    s.status = "expired"
                applied += 1
            # Stale-turn_state cleanup: a non-active row stuck at 'processing'
            # (e.g. backfilled from a crash by migration 003) is repaired here —
            # an explicit write, not an inference at read time.
            if s.turn_state == "processing" and s.status != "active":
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
        if status:
            q = q.where(LedgerSession.status == status)
        rows = (await self.db.execute(q)).scalars().all()
        now = datetime.utcnow()
        out = [self._repr(s, now) for s in rows]
        if relevant is not None:
            out = [r for r in out if r["relevant"] == relevant]
        out.sort(key=lambda r: r["last_event_at"] or "", reverse=True)
        return out

    async def board(self, user_id: int) -> dict:
        """The data structure the BotBeam board view is built from.

        Sessions: relevant only. Ordering guarantee (rev 18): active sessions
        first in STABLE order — first_seen ascending, so a card never moves
        while its session stays active and new activations append at the end —
        then inactive by last_event_at descending. Events and products ship
        empty in phase 1 — the record plane lands in phase 2.
        """
        now = datetime.utcnow()
        sessions = await self.list(user_id, relevant=True)   # last_event_at desc
        active = [r for r in sessions if r["status"] == "active"]
        active.sort(key=lambda r: r["first_seen"] or "")
        inactive = [r for r in sessions if r["status"] != "active"]
        return {"sessions": active + inactive, "events": [], "products": [], "as_of": _iso(now)}

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
