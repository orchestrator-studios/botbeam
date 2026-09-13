"""The ledger service — telemetry plane + record plane (The Ledger Book rev 19).

Two planes, one store, one writer (this service):

TELEMETRY — sessions. Both statuses are STORED, written by exactly one writer
per transition (Book rev 17 + 18) — nothing lifecycle is derived at read time:

  turn_state (waiting|processing) — UserPromptSubmit → processing, Stop /
  SessionEnd → waiting. The hook plane's alone; event emission never touches it.

  status (active|dormant|archived|expired) — every hook signal except
  SessionEnd → active (this is what un-archives and un-expires); SessionEnd →
  dormant; POST /archive → archived (409 while active); POST /unarchive →
  dormant; the sweep → expired at N consecutive transcript misses.
  A crashed session keeps status='active' — an accepted known gap until a
  sweep-repair mechanism lands; deliberately no inference papers over it.

RECORD — events and streams, admitted by judgment (the skill). Events are
immutable and exist only via log_event, an atomic composite: append the event,
write the emitting session's liveness (invariant 9 — logging is a sign of
life; turn_state untouched), apply the optional stream update. Streams are
field-replaced, never merged; `meta` is a per-user built-in that never closes,
never attributes, and stays out of the orientation index.

Computed per read (display windows and filters only): activity (the glyph),
relevant (the board filter), staleness (fresh/aging/stale), and stream
attribution (a session's board label — never stored, so nothing can rebrand it).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from models import LedgerSession, LedgerStream, LedgerEvent

logger = logging.getLogger("botbeam.ledger")

# Lifecycle signals the hooks may send — a closed set (422 otherwise).
SIGNALS = {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd", "PostToolUse"}

# Run-vs-read classification is service policy, per the Book: hooks transmit
# every tool completion unclassified; only these refresh last_run_at.
MUTATING_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell"}

SLUG_RE = re.compile(r"^[a-z0-9-]+$")
META_STREAM = "meta"


class LedgerError(ValueError):
    """Invalid ledger request — surfaced as a 422."""


class NotFound(ValueError):
    """Unknown referenced object — surfaced as a 404."""


class Conflict(ValueError):
    """State conflict — surfaced as a 409."""


class SessionActive(Conflict):
    """Archive refused because the session is active."""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _label(cwd: Optional[str], sid: str) -> Optional[str]:
    if not cwd:
        return None
    base = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or cwd
    return f"{base}·{sid[:6]}"


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").lower()


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

    @staticmethod
    def staleness(st: LedgerStream, now: Optional[datetime] = None) -> Optional[str]:
        """fresh ≤3d · aging 4–14d · stale >14d — null when closed."""
        if st.closed_at is not None:
            return None
        now = now or datetime.utcnow()
        days = (now - st.updated).days
        if days <= 3:
            return "fresh"
        if days <= 14:
            return "aging"
        return "stale"

    def _repr(self, s: LedgerSession, now: Optional[datetime] = None,
              stream_id: Optional[str] = None) -> dict:
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
            "stream_id": stream_id,
            "activity": self.activity(s, now),
            "relevant": bool(s.ever_prompted) and s.status not in ("archived", "expired"),
        }

    @staticmethod
    def _stream_repr(st: LedgerStream, now: Optional[datetime] = None) -> dict:
        return {
            "id": st.id,
            "title": st.title,
            "state": st.state,
            "next_action": st.next_action,
            "open_loops": st.open_loops or [],
            "working_paths": st.working_paths or [],
            "since": _iso(st.since),
            "updated": _iso(st.updated),
            "closed_at": _iso(st.closed_at),
            "staleness": LedgerService.staleness(st, now),
        }

    @staticmethod
    def _event_repr(e: LedgerEvent) -> dict:
        return {
            "id": e.id,
            "at": _iso(e.at),
            "stream_id": e.stream_id,
            "headline": e.headline,
            "body": e.body or [],
            "session_id": e.session_id,
        }

    # ── signals (telemetry plane) ────────────────────────────────────────────

    async def apply_event(
        self, user_id: int, sid: str, event: str,
        cwd: Optional[str] = None, machine: Optional[str] = None,
        tool: Optional[dict] = None,
    ) -> dict:
        if event not in SIGNALS:
            raise LedgerError(f'Unknown signal "{event}". Must be one of: {", ".join(sorted(SIGNALS))}')
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

        self._liveness(s, now, is_session_end=(event == "SessionEnd"))

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
        logger.debug("ledger signal %s (session=%s, user=%s)", event, sid[:6], user_id)
        return self._repr(s, now, stream_id=await self._attribution_one(user_id, s))

    @staticmethod
    def _liveness(s: LedgerSession, now: datetime, is_session_end: bool = False) -> None:
        """The universal writes: heartbeat, expiry-fact resets, and the status.
        Every signal but SessionEnd declares the session active — the explicit
        un-archive / un-expire (rev 18), not a derivation. Event emission
        counts as a signal here (invariant 9) and never touches turn_state."""
        s.last_event_at = now
        s.transcript_missing_since = None
        s.sweep_miss_count = 0
        if is_session_end:
            s.status = "dormant"
        else:
            if s.status == "archived":
                s.archived_at = None
            s.status = "active"

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

    # ── record plane: events ─────────────────────────────────────────────────

    async def log_event(
        self, user_id: int,
        stream_id: str, headline: str, body: list[str], session_id: str,
        stream_update: Optional[dict] = None,
        create_stream: Optional[dict] = None,
    ) -> dict:
        """POST /ledger/events — one atomic transaction, three parts: append
        the immutable event; write the emitting session's liveness (invariant
        9 — turn_state untouched); apply the stream update / creation. All
        validation precedes every write, and one commit lands the composite —
        it commits entirely or not at all.
        """
        now = datetime.utcnow()

        # ── validate everything first — no partial writes ──
        if not headline or not headline.strip():
            raise LedgerError("headline must be non-empty")
        if "\n" in headline or "\r" in headline:
            raise LedgerError("headline must be a single line")
        if not isinstance(body, list) or not (1 <= len(body) <= 4) \
                or not all(isinstance(b, str) and b.strip() for b in body):
            raise LedgerError("body must be 1-4 non-empty markdown strings")
        if not session_id:
            raise LedgerError("session_id is required — every event has exactly one emitter")
        if not SLUG_RE.match(stream_id or ""):
            raise LedgerError("stream_id must be a slug ([a-z0-9-]+)")
        if stream_update:
            self._check_stream_fields(stream_update)

        s = await self.db.get(LedgerSession, session_id)
        if s is None or s.user_id != user_id:
            raise NotFound(f'Unknown session "{session_id}"')

        st = await self._get_stream(user_id, stream_id)
        if st is None and stream_id == META_STREAM:
            st = await self._ensure_meta(user_id, now)
        if st is None:
            if create_stream is None:
                raise NotFound(f'Unknown stream "{stream_id}" — pass create_stream to create it')
            st = LedgerStream(
                user_id=user_id, id=stream_id,
                title=create_stream.get("title"),
                working_paths=create_stream.get("working_paths"),
                since=now, updated=now,
            )
            self.db.add(st)
        elif st.closed_at is not None:
            raise Conflict(f'Stream "{stream_id}" is closed')

        # ── writes — committed together below ──
        ev = LedgerEvent(
            id=f"ev_{uuid.uuid4().hex[:16]}", user_id=user_id, at=now,
            stream_id=stream_id, headline=headline.strip(), body=body,
            session_id=session_id,
        )
        self.db.add(ev)

        self._liveness(s, now)   # invariant 9: emitting is a sign of life

        if stream_update:
            self._apply_stream_fields(st, stream_update)
        st.updated = now

        await self.db.commit()
        await self.db.refresh(s)
        await self.db.refresh(st)
        logger.info("ledger event logged (stream=%s, session=%s, user=%s)",
                    stream_id, session_id[:6], user_id)
        return {
            "event": self._event_repr(ev),
            "session": self._repr(s, now, stream_id=await self._attribution_one(user_id, s)),
            "stream": self._stream_repr(st, now),
        }

    async def events_list(
        self, user_id: int,
        stream_id: Optional[str] = None, session_id: Optional[str] = None,
        since: Optional[datetime] = None, limit: int = 100,
    ) -> list[dict]:
        q = select(LedgerEvent).where(LedgerEvent.user_id == user_id)
        if stream_id:
            q = q.where(LedgerEvent.stream_id == stream_id)
        if session_id:
            q = q.where(LedgerEvent.session_id == session_id)
        if since:
            q = q.where(LedgerEvent.at >= since)
        q = q.order_by(LedgerEvent.at.desc(), LedgerEvent.id.desc()).limit(limit)
        rows = (await self.db.execute(q)).scalars().all()
        return [self._event_repr(e) for e in rows]

    # ── record plane: streams ────────────────────────────────────────────────

    async def stream_put(self, user_id: int, sid: str, fields: dict) -> dict:
        """Create a stream or replace the given fields of its record."""
        if not SLUG_RE.match(sid or ""):
            raise LedgerError("stream id must be a slug ([a-z0-9-]+)")
        now = datetime.utcnow()
        st = await self._get_stream(user_id, sid)
        if st is None and sid == META_STREAM:
            st = await self._ensure_meta(user_id, now)
        if st is None:
            st = LedgerStream(user_id=user_id, id=sid, since=now, updated=now)
            self.db.add(st)
        elif st.closed_at is not None:
            raise Conflict(f'Stream "{sid}" is closed')
        self._apply_stream_fields(st, fields)
        st.updated = now
        await self.db.commit()
        await self.db.refresh(st)
        return self._stream_repr(st, now)

    async def stream_close(
        self, user_id: int, sid: str, reason: str,
        session_id: Optional[str] = None,
    ) -> dict:
        """Close a stream and log the closure event — one transaction. The
        closure event's emitter is optional (flagged to the Book: the spec's
        close body carries only `reason`, but events require an emitter)."""
        if sid == META_STREAM:
            raise Conflict("the meta stream never closes")
        st = await self._get_stream(user_id, sid)
        if st is None:
            raise NotFound(f'Unknown stream "{sid}"')
        if st.closed_at is not None:
            raise Conflict(f'Stream "{sid}" is already closed')
        s = None
        if session_id:
            s = await self.db.get(LedgerSession, session_id)
            if s is None or s.user_id != user_id:
                raise NotFound(f'Unknown session "{session_id}"')
        now = datetime.utcnow()
        st.closed_at = now
        st.updated = now
        ev = LedgerEvent(
            id=f"ev_{uuid.uuid4().hex[:16]}", user_id=user_id, at=now,
            stream_id=sid, headline=f'Stream "{sid}" closed — {reason or "done"}',
            body=[reason or "closed"], session_id=session_id,
        )
        self.db.add(ev)
        if s is not None:
            self._liveness(s, now)
        await self.db.commit()
        await self.db.refresh(st)
        logger.info("ledger stream closed (%s, user=%s)", sid, user_id)
        return {"stream": self._stream_repr(st, now), "closure_event": self._event_repr(ev)}

    async def streams_list(self, user_id: int, status: str = "active") -> list[dict]:
        q = select(LedgerStream).where(LedgerStream.user_id == user_id)
        if status == "active":
            q = q.where(LedgerStream.closed_at.is_(None))
        elif status == "closed":
            q = q.where(LedgerStream.closed_at.is_not(None))
        rows = (await self.db.execute(q)).scalars().all()
        now = datetime.utcnow()
        out = [self._stream_repr(st, now) for st in rows]
        out.sort(key=lambda r: r["updated"] or "", reverse=True)
        return out

    # ── attribution (computed — never stored) ────────────────────────────────

    async def _attribution_one(self, user_id: int, s: LedgerSession) -> Optional[str]:
        m = await self._attributions(user_id, [s])
        return m.get(s.id)

    async def _attributions(self, user_id: int, rows: list[LedgerSession]) -> dict:
        """sid → stream_id per the Book's rule: the stream of the session's most
        recent non-meta event; else the most recently updated active stream
        whose working_paths contain the workspace; else None. Writes into the
        ledger itself never re-attribute (invariant 6) — meta is excluded."""
        ids = [s.id for s in rows]
        if not ids:
            return {}
        evq = (
            select(LedgerEvent.session_id, LedgerEvent.stream_id)
            .where(LedgerEvent.user_id == user_id,
                   LedgerEvent.session_id.in_(ids),
                   LedgerEvent.stream_id != META_STREAM)
            .order_by(LedgerEvent.at.desc(), LedgerEvent.id.desc())
        )
        out: dict = {}
        for sid, stream_id in (await self.db.execute(evq)).all():
            if sid not in out:
                out[sid] = stream_id
        remaining = [s for s in rows if s.id not in out and s.workspace_id]
        if remaining:
            stq = (
                select(LedgerStream)
                .where(LedgerStream.user_id == user_id,
                       LedgerStream.closed_at.is_(None),
                       LedgerStream.id != META_STREAM)
                .order_by(LedgerStream.updated.desc())
            )
            streams = (await self.db.execute(stq)).scalars().all()
            for s in remaining:
                ws = _norm_path(s.workspace_id)
                for st in streams:
                    if any(_norm_path(p) == ws for p in (st.working_paths or [])):
                        out[s.id] = st.id
                        break
        return out

    # ── search ───────────────────────────────────────────────────────────────

    async def search(self, user_id: int, q: str, limit: int = 25) -> list[dict]:
        """Substring search across events and streams — recall's endpoint.
        Headline/title hits rank above body/state hits; recency breaks ties."""
        needle = (q or "").strip().lower()
        if not needle:
            raise LedgerError("q is required")
        items = []
        events = (await self.db.execute(
            select(LedgerEvent).where(LedgerEvent.user_id == user_id)
            .order_by(LedgerEvent.at.desc()).limit(500)
        )).scalars().all()
        for e in events:
            hay_head = (e.headline or "").lower()
            hay_body = " ".join(e.body or []).lower()
            if needle in hay_head:
                items.append({"kind": "event", "score": 1.0, "at": e.at, "record": self._event_repr(e)})
            elif needle in hay_body:
                items.append({"kind": "event", "score": 0.6, "at": e.at, "record": self._event_repr(e)})
        streams = (await self.db.execute(
            select(LedgerStream).where(LedgerStream.user_id == user_id)
        )).scalars().all()
        now = datetime.utcnow()
        for st in streams:
            top = f"{st.id} {st.title or ''}".lower()
            rest = f"{st.state or ''} {st.next_action or ''} {' '.join(st.open_loops or [])}".lower()
            if needle in top:
                items.append({"kind": "stream", "score": 1.0, "at": st.updated, "record": self._stream_repr(st, now)})
            elif needle in rest:
                items.append({"kind": "stream", "score": 0.6, "at": st.updated, "record": self._stream_repr(st, now)})
        items.sort(key=lambda r: (-r["score"], -(r["at"].timestamp() if r["at"] else 0)))
        return [{"kind": r["kind"], "score": r["score"], "record": r["record"]} for r in items[:limit]]

    # ── views ────────────────────────────────────────────────────────────────

    async def index_md(self, user_id: int) -> str:
        """GET /ledger/index — the one-screen orientation, service-rendered
        markdown, injected at session start. The meta stream stays out of it."""
        now = datetime.utcnow()
        streams = [r for r in await self.streams_list(user_id, status="active")
                   if r["id"] != META_STREAM]
        events = await self.events_list(user_id, limit=8)
        lines = [f"# Ledger orientation — {now.date().isoformat()}", ""]
        lines.append("## Active streams")
        if streams:
            for r in streams:
                bits = [f"**{r['title'] or r['id']}**"]
                if r["staleness"] and r["staleness"] != "fresh":
                    bits[0] += f" ({r['staleness']})"
                if r["state"]:
                    bits.append(r["state"])
                if r["next_action"]:
                    bits.append(f"next: {r['next_action']}")
                lines.append(f"- {' — '.join(bits)}")
                for loop in (r["open_loops"] or [])[:3]:
                    lines.append(f"  - open: {loop}")
        else:
            lines.append("- (no active streams)")
        lines += ["", "## Recent activity"]
        if events:
            for e in events:
                day = (e["at"] or "")[:10]
                lines.append(f"- {day} · {e['stream_id']} · {e['headline']}")
        else:
            lines.append("- (no events logged yet)")
        return "\n".join(lines) + "\n"

    # ── reads ────────────────────────────────────────────────────────────────

    async def list(
        self, user_id: int,
        status: Optional[str] = None, machine: Optional[str] = None,
        relevant: Optional[bool] = None, stream_id: Optional[str] = None,
    ) -> list[dict]:
        q = select(LedgerSession).where(LedgerSession.user_id == user_id)
        if machine:
            q = q.where(LedgerSession.machine == machine)
        if status:
            q = q.where(LedgerSession.status == status)
        rows = (await self.db.execute(q)).scalars().all()
        now = datetime.utcnow()
        attr = await self._attributions(user_id, rows)
        out = [self._repr(s, now, stream_id=attr.get(s.id)) for s in rows]
        if relevant is not None:
            out = [r for r in out if r["relevant"] == relevant]
        if stream_id:
            out = [r for r in out if r["stream_id"] == stream_id]
        out.sort(key=lambda r: r["last_event_at"] or "", reverse=True)
        return out

    async def board(self, user_id: int) -> dict:
        """The data structure the BotBeam board view is built from.

        Sessions: relevant only. Ordering guarantee (rev 18): active sessions
        first in STABLE order — first_seen ascending, so a card never moves
        while its session stays active and new activations append at the end —
        then inactive by last_event_at descending. Plus the record plane
        (rev 19): recent events (rendered below the session sections) and the
        active streams that label them. Products are absent by decision.
        """
        now = datetime.utcnow()
        sessions = await self.list(user_id, relevant=True)   # last_event_at desc
        active = [r for r in sessions if r["status"] == "active"]
        active.sort(key=lambda r: r["first_seen"] or "")
        inactive = [r for r in sessions if r["status"] != "active"]
        return {
            "sessions": active + inactive,
            "events": await self.events_list(user_id, limit=20),
            "streams": await self.streams_list(user_id, status="active"),
            "as_of": _iso(now),
        }

    # ── test support ─────────────────────────────────────────────────────────

    async def reset(self, user_id: int) -> int:
        """Truncate the caller's ledger rows — all three stores. Test-only
        (LEDGER_ADMIN_RESET)."""
        await self.db.execute(delete(LedgerEvent).where(LedgerEvent.user_id == user_id))
        await self.db.execute(delete(LedgerStream).where(LedgerStream.user_id == user_id))
        res = await self.db.execute(delete(LedgerSession).where(LedgerSession.user_id == user_id))
        await self.db.commit()
        logger.info("ledger reset (%s sessions, user=%s)", res.rowcount, user_id)
        return res.rowcount or 0

    # ── internals ────────────────────────────────────────────────────────────

    async def _own(self, user_id: int, sid: str) -> LedgerSession:
        s = await self.db.get(LedgerSession, sid)
        if s is None or s.user_id != user_id:
            raise NotFound("Session not found")
        return s

    async def _get_stream(self, user_id: int, sid: str) -> Optional[LedgerStream]:
        return (await self.db.execute(
            select(LedgerStream).where(LedgerStream.user_id == user_id, LedgerStream.id == sid)
        )).scalar_one_or_none()

    async def _ensure_meta(self, user_id: int, now: datetime) -> LedgerStream:
        """The built-in per-user meta stream, created lazily on first reference."""
        st = LedgerStream(user_id=user_id, id=META_STREAM, title="Ledger system",
                          since=now, updated=now)
        self.db.add(st)
        return st

    @staticmethod
    def _check_stream_fields(fields: dict) -> None:
        allowed = {"title", "state", "next_action", "open_loops", "working_paths"}
        unknown = set(fields) - allowed
        if unknown:
            raise LedgerError(f"unknown stream field(s): {', '.join(sorted(unknown))}")

    @staticmethod
    def _apply_stream_fields(st: LedgerStream, fields: dict) -> None:
        LedgerService._check_stream_fields(fields)
        for k, v in fields.items():
            setattr(st, k, v)
