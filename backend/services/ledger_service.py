"""The ledger service — telemetry plane + record plane (The Ledger Book rev 19).

Two planes, one store, one writer (this service):

TELEMETRY — sessions. Both statuses are STORED, written by exactly one writer
per transition (Book rev 17 + 18) — nothing lifecycle is derived at read time:

  turn_state (waiting|processing) — UserPromptSubmit → processing, Stop /
  SessionEnd → waiting. The hook plane's alone; event emission never touches it.

  status (active|dormant|archived — three states, no fourth since rev 20) —
  every hook signal except SessionEnd → active (this is what un-archives);
  SessionEnd → dormant; POST /archive → archived (409 while active);
  POST /unarchive → dormant. A crashed session keeps status='active' — an
  accepted known gap until a repair mechanism lands; deliberately no
  inference papers over it. Expiry and the sweep were retired outright: a
  transcript aging off one machine's disk was never a state of the session.

RECORD — events, streams, runs, and deliverables, admitted by judgment (the
skill). Events are immutable and exist only via log_event, an atomic
composite: append the event, write a session emitter's liveness
(invariant 9 — logging is a sign of life; turn_state untouched), apply the
optional stream update. Every write that records who acted takes an ACTOR
(invariant 11) — one prefixed identifier, not a pair of fields: the type is
a property of the identifier itself. "session:<id>" resolves to a session
and writes its liveness; "board" is the one BotBeam interface per user —
its own identity, no id, no liveness row. Declared by the caller, never
inferred from the credential. Admitting a new actor type is a line in
ACTOR_SINGLETONS or a new prefix branch, never a migration. Streams are field-replaced, never merged. There is no
built-in stream and no slug the code knows by name — work on the ledger
itself is a stream like any other, or it is not logged.

Runs and deliverables (rev 21): a Run is a bounded stretch of work on exactly
one Deliverable, declared at BOTH ends (invariant 10) — opened and closed by
explicit calls, never timed out; ended_at IS NULL is the board's ⚡, a plain
query with no window arithmetic. Opening and closing both write the session's
liveness (invariant 9 extends). A Deliverable persists and is advanced: its
`state` is rewritten whole by each closing run; its live|retired status is the
USER'S call via retire/unretire, never Claude's, never a run outcome. The old
computed run glyph (last_run_at inside a decaying window, fed by PostToolUse
against a mutating-tool list) is deleted — it inferred state from a clock and
was inverted for the case it existed to show. PostToolUse remains as a pure
heartbeat.

Computed per read (display windows and filters only): activity (the circle),
open_run (a JOIN, not a computation — the bolt), relevant (the board filter),
staleness (fresh/aging/stale), and stream attribution (a session's board
label — never stored, so nothing can rebrand it).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import LedgerSession, LedgerStream, LedgerEvent, LedgerRun, LedgerDeliverable

logger = logging.getLogger("botbeam.ledger")

# Lifecycle signals the hooks may send — a closed set (422 otherwise).
# PostToolUse is a pure heartbeat since rev 21: nothing consumes the tool
# payload, but the in-turn liveness signal stays (recency through long turns,
# and the future crash repair needs a sensor to tell "crashed mid-run" from
# "ten-minute build").
SIGNALS = {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd", "PostToolUse"}

SLUG_RE = re.compile(r"^[a-z0-9-]+$")

# Recognised actor types (invariant 11). "session:<id>" is the prefixed kind;
# singletons carry no id because there is exactly one per user. Admitting a
# new actor type is a line here, not a migration.
ACTOR_SESSION = "session"
ACTOR_SINGLETONS = {"board"}


class UnknownActorType(ValueError):
    """An actor whose type the code does not recognise — 400, not 422: the
    request parses, the type just isn't admitted (yet)."""


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
        """Active sessions' circle: the stored turn_state, nothing more. The
        bolt is a separate channel (open_run — a join on declared runs) since
        rev 21; the two render independently and all four combinations are
        legal. None off the active band."""
        if s.status != "active":
            return None
        return s.turn_state

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
              stream_id: Optional[str] = None, open_run: Optional[dict] = None) -> dict:
        """The Session wire representation: stored facts + computed display
        fields. open_run is a JOIN, not a computation — the caller resolves it
        (bulk in list(), singly elsewhere)."""
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
            "ended_at": _iso(s.ended_at),
            "ever_prompted": bool(s.ever_prompted),
            "archived_at": _iso(s.archived_at),
            "status": s.status,
            "stream_id": stream_id,
            "open_run": open_run,
            "activity": self.activity(s, now),
            "relevant": bool(s.ever_prompted) and s.status != "archived",
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
    def _run_repr(r: LedgerRun, now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        end = r.ended_at or now
        return {
            "id": r.id,
            "deliverable_id": r.deliverable_id,
            "session_id": r.session_id,
            "intent": r.intent,
            "started_at": _iso(r.started_at),
            "ended_at": _iso(r.ended_at),
            "outcome": r.outcome,
            "elapsed_s": max(0, int((end - r.started_at).total_seconds())),
        }

    @staticmethod
    def _deliverable_repr(d: LedgerDeliverable) -> dict:
        return {
            "id": d.id,
            "at": _iso(d.at),
            "name": d.name,
            "home": d.home,
            "state": d.state,
            "status": d.status,
            "stream_id": d.stream_id,
            "last_run_id": d.last_run_id,
            "updated": _iso(d.updated),
        }

    @staticmethod
    def _event_repr(e: LedgerEvent) -> dict:
        return {
            "id": e.id,
            "at": _iso(e.at),
            "stream_id": e.stream_id,
            "headline": e.headline,
            "body": e.body or [],
            "actor": e.actor,
        }

    # ── the actor (invariant 11) ─────────────────────────────────────────────

    @staticmethod
    def _parse_actor(actor: Optional[str]) -> tuple[str, Optional[str]]:
        """One prefixed identifier — parse on the first ':'. No colon means
        the type has exactly one instance and is its own identity. Returns
        (type, id-or-None); unrecognised types are 400 (UnknownActorType),
        an unparseable or missing actor is 422 (LedgerError)."""
        if not actor or not isinstance(actor, str) or not actor.strip():
            raise LedgerError('actor is required — "session:<id>", or "board"')
        actor = actor.strip()
        if ":" in actor:
            kind, _, ident = actor.partition(":")
            if kind == ACTOR_SESSION:
                if not ident:
                    raise LedgerError('session actor needs an id — "session:<id>"')
                return ACTOR_SESSION, ident
            raise UnknownActorType(f'Unknown actor type "{kind}"')
        if actor in ACTOR_SINGLETONS:
            return actor, None
        raise UnknownActorType(f'Unknown actor "{actor}"')

    async def _resolve_actor(self, user_id: int, actor: Optional[str]
                             ) -> tuple[str, Optional[LedgerSession]]:
        """(canonical actor string, session row or None). A session actor
        must resolve to one of this user's sessions; singleton actors resolve
        to themselves with nothing to look up."""
        kind, ident = self._parse_actor(actor)
        if kind == ACTOR_SESSION:
            s = await self.db.get(LedgerSession, ident)
            if s is None or s.user_id != user_id:
                raise NotFound(f'Unknown session "{ident}"')
            return f"{ACTOR_SESSION}:{ident}", s
        return kind, None

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

        # Workspace refreshes; the label is first-write-wins. A card must not
        # rename itself mid-life when the shell cd's into a subdirectory.
        if cwd:
            s.workspace_id = cwd
            if not s.label:
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
        # PostToolUse: pure heartbeat — the universal writes above are the
        # whole effect; the tool payload is accepted and ignored (rev 21).

        await self.db.commit()
        await self.db.refresh(s)
        logger.debug("ledger signal %s (session=%s, user=%s)", event, sid[:6], user_id)
        return await self._repr_one(user_id, s, now)

    @staticmethod
    def _liveness(s: LedgerSession, now: datetime, is_session_end: bool = False) -> None:
        """The universal writes: heartbeat and the status. Every signal but
        SessionEnd declares the session active and clears archived_at — the
        explicit un-archive (rev 18), not a derivation. Event emission counts
        as a signal here (invariant 9) and never touches turn_state."""
        s.last_event_at = now
        if is_session_end:
            s.status = "dormant"
        else:
            s.status = "active"
            s.archived_at = None

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
        return await self._repr_one(user_id, s)

    async def unarchive(self, user_id: int, sid: str) -> dict:
        s = await self._own(user_id, sid)
        s.status = "dormant"
        s.archived_at = None
        await self.db.commit()
        await self.db.refresh(s)
        return await self._repr_one(user_id, s)

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

    # ── record plane: events ─────────────────────────────────────────────────

    async def log_event(
        self, user_id: int,
        stream_id: str, headline: str, body: list[str],
        actor: Optional[str] = None,
        stream_update: Optional[dict] = None,
        create_stream: Optional[dict] = None,
    ) -> dict:
        """POST /ledger/events — one atomic transaction, three parts: append
        the immutable event; for a session actor, write its liveness
        (invariant 9 — turn_state untouched; other actors have no liveness
        row); apply the stream update / creation. All validation precedes
        every write, and one commit lands the composite — it commits entirely
        or not at all.
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
        canonical, s = await self._resolve_actor(user_id, actor)
        if not SLUG_RE.match(stream_id or ""):
            raise LedgerError("stream_id must be a slug ([a-z0-9-]+)")
        if stream_update:
            self._check_stream_fields(stream_update)

        st = await self._get_stream(user_id, stream_id)
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
            actor=canonical,
        )
        self.db.add(ev)

        if s is not None:
            self._liveness(s, now)   # invariant 9: session emission is a sign of life

        if stream_update:
            self._apply_stream_fields(st, stream_update)
        st.updated = now

        await self.db.commit()
        if s is not None:
            await self.db.refresh(s)
        await self.db.refresh(st)
        logger.info("ledger event logged (stream=%s, actor=%s, user=%s)",
                    stream_id, canonical[:14], user_id)
        return {
            "event": self._event_repr(ev),
            "session": await self._repr_one(user_id, s, now) if s is not None else None,
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
            # The filter stays a bare uuid — the parameter name already
            # declared the type (invariant 11 ruling).
            q = q.where(LedgerEvent.actor == f"{ACTOR_SESSION}:{session_id}")
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

    async def stream_close(self, user_id: int, sid: str, reason: str,
                           actor: Optional[str] = None) -> dict:
        """Close a stream and log the closure event — one transaction. The
        actor is required with no exceptions: closure events are events, and
        every event names who acted (invariant 11) — a session (whose
        liveness is written, invariant 9) or the board."""
        st = await self._get_stream(user_id, sid)
        if st is None:
            raise NotFound(f'Unknown stream "{sid}"')
        if st.closed_at is not None:
            raise Conflict(f'Stream "{sid}" is already closed')
        canonical, s = await self._resolve_actor(user_id, actor)
        now = datetime.utcnow()
        st.closed_at = now
        st.updated = now
        ev = LedgerEvent(
            id=f"ev_{uuid.uuid4().hex[:16]}", user_id=user_id, at=now,
            stream_id=sid, headline=f'Stream "{sid}" closed — {reason or "done"}',
            body=[reason or "closed"], actor=canonical,
        )
        self.db.add(ev)
        if s is not None:
            self._liveness(s, now)
        await self.db.commit()
        await self.db.refresh(st)
        logger.info("ledger stream closed (%s, actor=%s, user=%s)", sid, canonical[:14], user_id)
        return {"stream": self._stream_repr(st, now), "closure_event": self._event_repr(ev)}

    async def stream_reopen(self, user_id: int, sid: str, reason: str,
                            actor: Optional[str] = None) -> dict:
        """Reopen a closed stream and log the reopen event — one transaction,
        the mirror of stream_close, same actor rule (invariant 11). The
        record keeps both the closure and the reopen; nothing is erased. The
        stream returns to the board and brings its events and deliverables
        back with it (the board invariant does that for free)."""
        st = await self._get_stream(user_id, sid)
        if st is None:
            raise NotFound(f'Unknown stream "{sid}"')
        if st.closed_at is None:
            raise Conflict(f'Stream "{sid}" is not closed')
        canonical, s = await self._resolve_actor(user_id, actor)
        now = datetime.utcnow()
        st.closed_at = None
        st.updated = now
        ev = LedgerEvent(
            id=f"ev_{uuid.uuid4().hex[:16]}", user_id=user_id, at=now,
            stream_id=sid, headline=f'Stream "{sid}" reopened — {reason or "back on the board"}',
            body=[reason or "reopened"], actor=canonical,
        )
        self.db.add(ev)
        if s is not None:
            self._liveness(s, now)
        await self.db.commit()
        await self.db.refresh(st)
        logger.info("ledger stream reopened (%s, actor=%s, user=%s)", sid, canonical[:14], user_id)
        return {"stream": self._stream_repr(st, now), "reopen_event": self._event_repr(ev)}

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

    # ── record plane: runs + deliverables (rev 21) ───────────────────────────

    async def run_open(
        self, user_id: int, actor: str, intent: str,
        deliverable_id: Optional[str] = None,
        create_deliverable: Optional[dict] = None,
    ) -> dict:
        """POST /ledger/runs — the only way a run (or a deliverable) comes
        into existence. Atomic: run + optional deliverable mint + the opening
        session's liveness (invariant 9 extends; turn_state untouched). The
        opener must be a session actor: a run is a stretch of WORK, and the
        board doesn't do the work — it watches it."""
        now = datetime.utcnow()
        if not intent or not intent.strip():
            raise LedgerError("intent is required — what this work IS, not how big it is")
        if bool(deliverable_id) == bool(create_deliverable):
            raise LedgerError("pass exactly one of deliverable_id or create_deliverable")

        canonical, s = await self._resolve_actor(user_id, actor)
        if s is None:
            raise LedgerError(f'a run is opened by a session — "{canonical}" does not do the work')
        session_id = s.id

        # One open run per session — forces an honest close-or-abandon at the
        # boundary. Recovery after a crash: list your open runs, abandon the
        # stale one, open the new one.
        existing = await self._open_run_row(user_id, session_id)
        if existing is not None:
            raise Conflict(f'session already has an open run ("{existing.intent}", {existing.id})')

        if deliverable_id:
            d = await self.db.get(LedgerDeliverable, deliverable_id)
            if d is None or d.user_id != user_id:
                raise NotFound(f'Unknown deliverable "{deliverable_id}"')
            if d.status == "retired":
                raise Conflict(f'Deliverable "{d.name}" is retired — unretire it first')
        else:
            name = (create_deliverable or {}).get("name")
            home = (create_deliverable or {}).get("home")
            stream_id = (create_deliverable or {}).get("stream_id")
            if not name or not home or not stream_id:
                raise LedgerError("create_deliverable needs name, home, and stream_id")
            st = await self._get_stream(user_id, stream_id)
            if st is None:
                # No nested create_stream — PUT /ledger/streams/{id} is the
                # create path; one call beforehand (rev 21 ruling).
                raise NotFound(f'Unknown stream "{stream_id}" — create it first (PUT /ledger/streams/{{id}})')
            d = LedgerDeliverable(
                id=f"dl_{uuid.uuid4().hex[:16]}", user_id=user_id, at=now,
                name=name, home=home, stream_id=stream_id, updated=now,
            )
            self.db.add(d)

        run = LedgerRun(
            id=f"run_{uuid.uuid4().hex[:16]}", user_id=user_id,
            deliverable_id=d.id, session_id=session_id,
            intent=intent.strip(), started_at=now,
        )
        self.db.add(run)
        self._liveness(s, now)
        await self.db.commit()
        logger.info("ledger run opened (%s, deliverable=%s, session=%s, user=%s)",
                    run.id, d.id, session_id[:6], user_id)
        return {
            "run": self._run_repr(run, now),
            "deliverable": self._deliverable_repr(d),
            "session": await self._repr_one(user_id, s, now),
        }

    async def run_close(
        self, user_id: int, run_id: str, actor: str,
        outcome: str, state: Optional[str] = None,
    ) -> dict:
        """POST /ledger/runs/{id}/close — the only way a run ends. The closer
        may differ from the opener (ruling: that IS the manual cleanup path
        for crash-leaked runs), and the board may close — sweeping a leaked
        run off a card is exactly a dashboard act. closed advances the
        deliverable; abandoned leaves it untouched."""
        run = await self.db.get(LedgerRun, run_id)
        if run is None or run.user_id != user_id:
            raise NotFound(f'Unknown run "{run_id}"')
        if run.ended_at is not None:
            raise Conflict(f'Run "{run_id}" is already ended ({run.outcome})')
        if outcome not in ("closed", "abandoned"):
            raise LedgerError('outcome must be "closed" or "abandoned"')
        if outcome == "closed" and (state is None or not state.strip()):
            raise LedgerError("state is required on closed — the closer must consider it (resubmitting it verbatim is legitimate)")
        if outcome == "abandoned" and state is not None:
            raise LedgerError("state is refused on abandoned — the deliverable is untouched")
        canonical, s = await self._resolve_actor(user_id, actor)

        now = datetime.utcnow()
        run.ended_at = now
        run.outcome = outcome
        d = await self.db.get(LedgerDeliverable, run.deliverable_id)
        if outcome == "closed":
            d.state = state.strip()
            d.last_run_id = run.id
            d.updated = now
        if s is not None:
            self._liveness(s, now)
        await self.db.commit()
        logger.info("ledger run %s (%s, actor=%s, user=%s)", outcome, run_id, canonical[:14], user_id)
        return {
            "run": self._run_repr(run, now),
            "deliverable": self._deliverable_repr(d),
            "session": await self._repr_one(user_id, s, now) if s is not None else None,
        }

    async def deliverable_set_status(self, user_id: int, dl_id: str, retired: bool,
                                     actor: Optional[str] = None) -> dict:
        """retire / unretire — the USER'S call, never Claude's (rev 21 ruling:
        a run ending says nothing about whether the thing is finished with).
        The actor (invariant 11) names who acted — a session writes liveness,
        the board is Cliff's button."""
        canonical, s = await self._resolve_actor(user_id, actor)
        d = await self.db.get(LedgerDeliverable, dl_id)
        if d is None or d.user_id != user_id:
            raise NotFound(f'Unknown deliverable "{dl_id}"')
        if retired:
            open_run = (await self.db.execute(
                select(LedgerRun).where(LedgerRun.user_id == user_id,
                                        LedgerRun.deliverable_id == dl_id,
                                        LedgerRun.ended_at.is_(None))
            )).scalars().first()
            if open_run is not None:
                raise Conflict(f'Deliverable has an open run ({open_run.id}) — close it first')
        d.status = "retired" if retired else "live"
        now = datetime.utcnow()
        d.updated = now
        if s is not None:
            self._liveness(s, now)
        await self.db.commit()
        logger.info("ledger deliverable %s (%s, actor=%s, user=%s)",
                    "retired" if retired else "unretired", dl_id, canonical[:14], user_id)
        return self._deliverable_repr(d)

    async def runs_list(
        self, user_id: int, open_only: bool = False,
        session_id: Optional[str] = None, deliverable_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        q = select(LedgerRun).where(LedgerRun.user_id == user_id)
        if open_only:
            q = q.where(LedgerRun.ended_at.is_(None))
        if session_id:
            q = q.where(LedgerRun.session_id == session_id)
        if deliverable_id:
            q = q.where(LedgerRun.deliverable_id == deliverable_id)
        q = q.order_by(LedgerRun.started_at.desc(), LedgerRun.id.desc()).limit(limit)
        rows = (await self.db.execute(q)).scalars().all()
        now = datetime.utcnow()
        return [self._run_repr(r, now) for r in rows]

    async def deliverables_list(
        self, user_id: int, stream_id: Optional[str] = None,
        status: str = "live", limit: int = 100,
    ) -> list[dict]:
        q = select(LedgerDeliverable).where(LedgerDeliverable.user_id == user_id)
        if stream_id:
            q = q.where(LedgerDeliverable.stream_id == stream_id)
        if status in ("live", "retired"):
            q = q.where(LedgerDeliverable.status == status)
        q = q.order_by(LedgerDeliverable.updated.desc()).limit(limit)
        rows = (await self.db.execute(q)).scalars().all()
        return [self._deliverable_repr(d) for d in rows]

    # ── open-run join (the ⚡ — stored facts, joined per read) ────────────────

    async def _open_run_row(self, user_id: int, session_id: str) -> Optional[LedgerRun]:
        return (await self.db.execute(
            select(LedgerRun).where(LedgerRun.user_id == user_id,
                                    LedgerRun.session_id == session_id,
                                    LedgerRun.ended_at.is_(None))
        )).scalars().first()

    async def _open_runs(self, user_id: int, rows: list[LedgerSession]) -> dict:
        """sid → open_run join dict ({id, intent, deliverable_id,
        deliverable_name, started_at, elapsed_s}) for the sessions given."""
        ids = [s.id for s in rows]
        if not ids:
            return {}
        runs = (await self.db.execute(
            select(LedgerRun).where(LedgerRun.user_id == user_id,
                                    LedgerRun.session_id.in_(ids),
                                    LedgerRun.ended_at.is_(None))
        )).scalars().all()
        if not runs:
            return {}
        dl_ids = {r.deliverable_id for r in runs}
        dls = (await self.db.execute(
            select(LedgerDeliverable).where(LedgerDeliverable.id.in_(dl_ids))
        )).scalars().all()
        names = {d.id: d.name for d in dls}
        now = datetime.utcnow()
        out: dict = {}
        for r in runs:
            out[r.session_id] = {
                "id": r.id,
                "intent": r.intent,
                "deliverable_id": r.deliverable_id,
                "deliverable_name": names.get(r.deliverable_id),
                "started_at": _iso(r.started_at),   # load-bearing
                "elapsed_s": max(0, int((now - r.started_at).total_seconds())),  # convenience
            }
        return out

    async def _repr_one(self, user_id: int, s: LedgerSession,
                        now: Optional[datetime] = None) -> dict:
        """Full single-session representation with both joins resolved."""
        open_runs = await self._open_runs(user_id, [s])
        return self._repr(s, now, stream_id=await self._attribution_one(user_id, s),
                          open_run=open_runs.get(s.id))

    # ── attribution (computed — never stored) ────────────────────────────────

    async def _attribution_one(self, user_id: int, s: LedgerSession) -> Optional[str]:
        m = await self._attributions(user_id, [s])
        return m.get(s.id)

    async def _attributions(self, user_id: int, rows: list[LedgerSession]) -> dict:
        """sid → stream_id per the Book's rule: the stream of the session's
        most recent event; else the most recently updated active stream whose
        working_paths contain the workspace; else None (invariant 6)."""
        ids = [s.id for s in rows]
        if not ids:
            return {}
        evq = (
            select(LedgerEvent.actor, LedgerEvent.stream_id)
            .where(LedgerEvent.user_id == user_id,
                   LedgerEvent.actor.in_([f"{ACTOR_SESSION}:{i}" for i in ids]))
            .order_by(LedgerEvent.at.desc(), LedgerEvent.id.desc())
        )
        out: dict = {}
        for actor, stream_id in (await self.db.execute(evq)).all():
            sid = actor.partition(":")[2]
            if sid not in out:
                out[sid] = stream_id
        remaining = [s for s in rows if s.id not in out and s.workspace_id]
        if remaining:
            stq = (
                select(LedgerStream)
                .where(LedgerStream.user_id == user_id,
                       LedgerStream.closed_at.is_(None))
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
        deliverables = (await self.db.execute(
            select(LedgerDeliverable).where(LedgerDeliverable.user_id == user_id)
        )).scalars().all()
        for d in deliverables:
            if needle in (d.name or "").lower():
                items.append({"kind": "deliverable", "score": 1.0, "at": d.updated, "record": self._deliverable_repr(d)})
            elif needle in f"{d.state or ''} {d.home or ''}".lower():
                items.append({"kind": "deliverable", "score": 0.6, "at": d.updated, "record": self._deliverable_repr(d)})
        items.sort(key=lambda r: (-r["score"], -(r["at"].timestamp() if r["at"] else 0)))
        return [{"kind": r["kind"], "score": r["score"], "record": r["record"]} for r in items[:limit]]

    # ── views ────────────────────────────────────────────────────────────────

    async def index_md(self, user_id: int) -> str:
        """GET /ledger/index — the one-screen orientation, service-rendered
        markdown, injected at session start. A view surface: everything shown
        references a stream that is shown (closed streams take their recent
        activity with them; the data endpoints still serve their history)."""
        now = datetime.utcnow()
        streams = await self.streams_list(user_id, status="active")
        open_ids = {r["id"] for r in streams}
        events = [e for e in await self.events_list(user_id, limit=40)
                  if e["stream_id"] in open_ids][:8]
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
        open_runs = await self._open_runs(user_id, rows)
        out = [self._repr(s, now, stream_id=attr.get(s.id), open_run=open_runs.get(s.id))
               for s in rows]
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
        (rev 19): recent events and the active streams that label them, and
        the live deliverables (rev 21) — rendered beside the streams, with
        the events feed below.

        Invariant: everything on the board references a stream that is on the
        board. Events and deliverables of a closed stream leave the view with
        it — rows unchanged, and the data endpoints (/ledger/events,
        /ledger/deliverables, /ledger/search) still serve them.
        """
        now = datetime.utcnow()
        sessions = await self.list(user_id, relevant=True)   # last_event_at desc
        active = [r for r in sessions if r["status"] == "active"]
        active.sort(key=lambda r: r["first_seen"] or "")
        inactive = [r for r in sessions if r["status"] != "active"]
        streams = await self.streams_list(user_id, status="active")
        open_ids = {r["id"] for r in streams}
        events = [e for e in await self.events_list(user_id, limit=60)
                  if e["stream_id"] in open_ids][:20]
        deliverables = [d for d in await self.deliverables_list(user_id, status="live")
                        if d["stream_id"] in open_ids]
        return {
            "sessions": active + inactive,
            "events": events,
            "streams": streams,
            "deliverables": deliverables,
            "as_of": _iso(now),
        }

    # ── test support ─────────────────────────────────────────────────────────

    async def reset(self, user_id: int) -> int:
        """Truncate the caller's ledger rows — all five stores. Test-only
        (LEDGER_ADMIN_RESET)."""
        await self.db.execute(delete(LedgerRun).where(LedgerRun.user_id == user_id))
        await self.db.execute(delete(LedgerDeliverable).where(LedgerDeliverable.user_id == user_id))
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
