from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    CheckConstraint, Column, Integer, String, Boolean, DateTime, Enum,
    ForeignKey, Text, UniqueConstraint, JSON,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Every table stores utf8mb4 so rich text (emoji, CJK, symbols, any language)
# round-trips losslessly. Binary assets live in object storage (S3), referenced
# here by URL — the DB stays text/metadata only.
_UTF8MB4 = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class UserRole(str, PyEnum):
    """Matches the kh / table-that role enum."""
    PLATFORM_ADMIN = "platform_admin"   # org_id = NULL; above all orgs
    ORG_ADMIN = "org_admin"             # manages their org's members
    MEMBER = "member"                   # regular user in an org


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = _UTF8MB4

    org_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = _UTF8MB4

    user_id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.org_id"), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)          # bcrypt hash
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x], name="userrole"),
        default=UserRole.MEMBER, nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    """A user-owned entry in the key-value store. Scoped directly to its owner.

    `kind` decides how it surfaces: 'display' entries are rendered live as tabs on
    the user's screen; 'lockbox' entries are stashed — written by the user or their
    agent in one context and retrieved in another — and listed separately rather
    than rendered. Both share one lifecycle: beam content, read it, archive when done.

    Names are unique per user (case-insensitive via utf8mb4_unicode_ci) — the
    agent resolves user-spoken names against them, so they must be unambiguous.
    Each user has exactly one default display (is_default) that always exists
    and can't be renamed, archived, or deleted.

    `description` is optional human-readable context — especially important for
    lockboxes, which aren't rendered, so the listing needs a summary of the payload.
    """
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_device_user_name"),
        _UTF8MB4,
    )

    id = Column(String(16), primary_key=True)              # public handle (the API/skill uses this)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)               # optional summary; key for lockboxes (not rendered)
    is_default = Column(Boolean, default=False, nullable=False)
    kind = Column(String(16), default="display", nullable=False)  # 'display' (rendered tab) | 'lockbox' (stashed)
    archived_at = Column(DateTime, nullable=True)          # non-null = off the display, restorable
    content_type = Column(String(20), nullable=True)
    content_body = Column(LONGTEXT, nullable=True)
    content_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeviceShare(Base):
    """A view-only grant of a device to another user.

    The device's owner creates these (by the grantee's email); the grantee then
    sees the device under "Shared with me" and watches its live content, but
    can't modify it — only the owner can beam/rename/archive/delete. Deleting the
    row revokes access. Rows cascade away when either the device or the grantee
    is removed. One row per (device, grantee); re-sharing is idempotent.
    """
    __tablename__ = "device_shares"
    __table_args__ = (
        UniqueConstraint("device_id", "grantee_user_id", name="uq_share_device_grantee"),
        _UTF8MB4,
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(16), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)
    grantee_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LedgerSession(Base):
    """One Claude Code session's stored facts — the ledger's telemetry plane.

    Statuses are STORED, per The Ledger Book (woodshed docs/ledger/): turn_state
    (waiting|processing) is set explicitly by signals (rev 17), and the lifecycle
    status (active|dormant|archived — three states, no fourth since rev 20) is
    written by its one writer per transition (rev 18) — hook signals, event
    emission, and archive calls. Nothing lifecycle is derived at read time; only
    display windows (the run bolt) and filters (relevant) are computed. Scoped
    to the owner like every other row; written only by LedgerService.
    """
    __tablename__ = "ledger_sessions"
    __table_args__ = _UTF8MB4

    id = Column(String(36), primary_key=True)                # the Claude Code session uuid
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id = Column(String(512), nullable=True)        # directory the session runs in (its workspace's id)
    machine = Column(String(128), nullable=True)
    label = Column(String(255), nullable=True)               # workspace basename + short session id
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    # STORED status, by decision (Ledger Book rev 17): UserPromptSubmit sets
    # 'processing', Stop/SessionEnd set 'waiting'. Declared by signals, never
    # inferred; the sweep repairs a crashed session's stale 'processing'.
    turn_state = Column(String(16), default="waiting", nullable=False)          # 'waiting' | 'processing'
    # STORED lifecycle status (Ledger Book rev 18; rev 20 retired 'expired' —
    # three states, no fourth): every signal except SessionEnd writes 'active'
    # (the explicit un-archive); SessionEnd writes 'dormant'; archive/unarchive
    # write 'archived'/'dormant'. A crashed session keeps 'active' — accepted
    # known gap until a repair mechanism lands; do not infer around it.
    status = Column(String(16), default="active", nullable=False)    # active|dormant|archived
    last_event_at = Column(DateTime, default=datetime.utcnow, nullable=False)   # heartbeat: every signal
    last_prompt_at = Column(DateTime, nullable=True)         # UserPromptSubmit
    last_stop_at = Column(DateTime, nullable=True)           # Stop (informational; turn_state carries the status)
    ended_at = Column(DateTime, nullable=True)               # SessionEnd (informational; status carries the lifecycle)
    ever_prompted = Column(Boolean, default=False, nullable=False)  # relevance gate — filters picker ghosts
    archived_at = Column(DateTime, nullable=True)            # when the user dismissed it; cleared when a signal re-activates


class LedgerStream(Base):
    """A named thread of work under management — the record plane (Book rev 19).

    The slug is the identity the API speaks (`stream_id` everywhere), unique per
    owner — hence the composite key. No slug is built-in or special — every
    stream closes, attributes, and appears in the index alike. Field-level
    replace only; the service never merges prose. Staleness (fresh/aging/stale)
    is computed on read, never stored.
    """
    __tablename__ = "ledger_streams"
    __table_args__ = _UTF8MB4

    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    id = Column(String(64), primary_key=True)                # the slug ([a-z0-9-]+)
    title = Column(String(255), nullable=True)
    state = Column(Text, nullable=True)                      # current-state narrative, rewritten freely
    next_action = Column(Text, nullable=True)                # the single step that resumes the work
    open_loops = Column(JSON, nullable=True)                 # string[]
    working_paths = Column(JSON, nullable=True)              # path[] — attribution hints
    since = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class LedgerEvent(Base):
    """Something that happened — immutable, append-only, server-stamped.

    Created only by POST /ledger/events (and stream close/reopen, which log
    their own). Never updated, never deleted. Carries exactly one stream (the
    slug, scoped to the same owner) and exactly one emitter — and an emitter
    is a PLACE (invariant 11): a session, or the BotBeam board. Session
    emission is a sign of life: the same transaction writes the emitter's
    liveness (invariant 9); the board is a surface, not a running thing, so
    board emission skips that and only that.
    """
    __tablename__ = "ledger_events"
    __table_args__ = (
        # The place is enforced, not preferred: a session emitter names its
        # session, a board emitter names none. Both or neither never lands.
        CheckConstraint(
            "(emitter_kind = 'session' AND session_id IS NOT NULL)"
            " OR (emitter_kind = 'board' AND session_id IS NULL)",
            name="ck_ledger_events_emitter_place"),
        _UTF8MB4,
    )

    id = Column(String(24), primary_key=True)                # "ev_" + hex, server-generated
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    stream_id = Column(String(64), nullable=False, index=True)  # owning stream's slug (per-owner scope)
    headline = Column(String(500), nullable=False)           # one line, past tense
    body = Column(JSON, nullable=False)                      # 1–4 markdown strings
    # Invariant 11: 'session' | 'board' — a stored fact, never inferred from
    # the credential (browser and agents authenticate as the same user), and
    # never encoded as a missing value.
    emitter_kind = Column(String(16), nullable=False, default="session")
    session_id = Column(String(36), ForeignKey("ledger_sessions.id", ondelete="CASCADE"), index=True, nullable=True)


class LedgerDeliverable(Base):
    """A thing that was made — record + link; the payload lives at its home.

    Persists and is ADVANCED (Book rev 21): `state` is mutable by design,
    rewritten whole by each closing run — events stay immutable, the mutation
    lives on the noun that was always going to change. Born only inside the
    run that needs it (POST /ledger/runs with create_deliverable); no direct
    create or update endpoint exists. `status` (live|retired) is declared by
    the user via retire/unretire — never by Claude, and never by a run ending.
    """
    __tablename__ = "ledger_deliverables"
    __table_args__ = _UTF8MB4

    id = Column(String(24), primary_key=True)                # "dl_" + hex, server-generated
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    at = Column(DateTime, default=datetime.utcnow, nullable=False)   # first registration
    name = Column(String(255), nullable=False)               # stable across its life
    home = Column(String(1024), nullable=False)              # canonical location — exactly one
    state = Column(Text, nullable=True)                      # where it stands — rewritten by closing runs
    status = Column(String(16), default="live", nullable=False)      # live|retired — user's call
    stream_id = Column(String(64), nullable=False, index=True)       # owning stream slug (per-owner scope)
    last_run_id = Column(String(24), nullable=True)          # the run that last advanced it
    updated = Column(DateTime, default=datetime.utcnow, nullable=False)


class LedgerRun(Base):
    """A bounded stretch of work against exactly one deliverable (Book rev 21).

    Declared at BOTH ends (invariant 10): started_at written by the open call,
    ended_at by the close — no timer, sweep, or heuristic may end a run.
    ended_at IS NULL is the definition of open; the board's ⚡ is a plain query
    on it, no window arithmetic. A crashed session leaks an open run — the same
    known gap as crashed-active, cleaned up by a non-opener close (allowed by
    ruling) until the repair mechanism lands.
    """
    __tablename__ = "ledger_runs"
    __table_args__ = _UTF8MB4

    id = Column(String(24), primary_key=True)                # "run_" + hex, server-generated
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    deliverable_id = Column(String(24), ForeignKey("ledger_deliverables.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id = Column(String(36), ForeignKey("ledger_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    intent = Column(String(500), nullable=False)             # what the work IS, not how big
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)               # null = open
    outcome = Column(String(16), nullable=True)              # closed|abandoned; null while open


class Memory(Base):
    """A durable, typed fact the user's agent writes and recalls later.

    Distinct from a Device: a memory isn't rendered (no tab) and isn't a one-off
    payload (lockbox) — it's a small, titled fact that accumulates and is recalled
    by relevance. Scoped directly to its owner.

    `key` is the stable public handle (unique per user, case-insensitive via
    utf8mb4_unicode_ci) the agent addresses and upserts by. `category` buckets it
    (see schemas.MemoryCategory); `description` is a one-line summary used for cheap
    recall listings (the body isn't returned when listing/searching).
    """
    __tablename__ = "memories"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_memory_user_key"),
        _UTF8MB4,
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    key = Column(String(255), nullable=False)              # stable public handle (the API/skill addresses by this)
    category = Column(String(32), default="note", nullable=False)
    description = Column(Text, nullable=True)              # one-line summary for recall listings
    body = Column(LONGTEXT, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
