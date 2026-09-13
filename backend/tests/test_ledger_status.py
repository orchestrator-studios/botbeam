"""Stored-status transition tests for LedgerService (Ledger Book rev 18).

Every lifecycle transition is an explicit write with one writer — these tests
drive the real service methods against an in-memory SQLite database (aiosqlite,
test-only dep; only the ledger_sessions table is created) and assert the stored
column plus the computed display fields (activity, relevant) and the board's
ordering guarantee. Run directly: venv/Scripts/python tests/test_ledger_status.py
"""
import asyncio
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config.settings import settings
from models import LedgerSession, LedgerStream, LedgerEvent, LedgerRun, LedgerDeliverable
from services.ledger_service import LedgerService, SessionActive

RESULTS: list[bool] = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS" if ok else f"FAIL {detail}"), "-", name)


async def main():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        for t in (LedgerSession.__table__, LedgerStream.__table__, LedgerEvent.__table__, LedgerDeliverable.__table__, LedgerRun.__table__):
            await conn.run_sync(t.create)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        svc = LedgerService(db)
        U = 1

        # ── signal writes ────────────────────────────────────────────────────
        r = await svc.apply_event(U, "sess-a", "SessionStart", cwd="/w/alpha", machine="m1")
        check("SessionStart creates row: status active, waiting, not relevant",
              r["status"] == "active" and r["activity"] == "waiting" and r["relevant"] is False, r)

        r = await svc.apply_event(U, "sess-a", "UserPromptSubmit")
        check("prompt -> processing, relevant",
              r["status"] == "active" and r["turn_state"] == "processing"
              and r["activity"] == "processing" and r["relevant"] is True, r)

        # PostToolUse is a pure heartbeat since rev 21 — the bolt is a declared
        # open run (its own suite), never a tool-completion inference.
        before = (await db.get(LedgerSession, "sess-a")).last_event_at
        r = await svc.apply_event(U, "sess-a", "PostToolUse", tool={"name": "Edit"})
        after = (await db.get(LedgerSession, "sess-a")).last_event_at
        check("PostToolUse -> heartbeat only (activity stays processing, no bolt)",
              r["activity"] == "processing" and r["open_run"] is None and after >= before, r)

        r = await svc.apply_event(U, "sess-a", "Stop")
        check("Stop -> waiting",
              r["turn_state"] == "waiting" and r["activity"] == "waiting", r)

        # ── archive is refused while active (409 path) ───────────────────────
        try:
            await svc.archive(U, "sess-a")
            check("archive while active -> SessionActive", False, "no exception")
        except SessionActive:
            check("archive while active -> SessionActive", True)

        # ── SessionEnd / resume ──────────────────────────────────────────────
        r = await svc.apply_event(U, "sess-a", "SessionEnd")
        check("SessionEnd -> dormant, activity None, ended_at set",
              r["status"] == "dormant" and r["activity"] is None and r["ended_at"], r)

        r = await svc.apply_event(U, "sess-a", "UserPromptSubmit")
        check("signal after SessionEnd -> active again (explicit write)",
              r["status"] == "active" and r["activity"] == "processing", r)

        # ── archive / unarchive / re-activate ────────────────────────────────
        await svc.apply_event(U, "sess-a", "SessionEnd")
        r = await svc.archive(U, "sess-a")
        check("archive dormant -> archived, archived_at set, not relevant",
              r["status"] == "archived" and r["archived_at"] and r["relevant"] is False, r)

        r = await svc.unarchive(U, "sess-a")
        check("unarchive -> dormant, archived_at cleared",
              r["status"] == "dormant" and r["archived_at"] is None, r)

        await svc.archive(U, "sess-a")
        r = await svc.apply_event(U, "sess-a", "Stop")
        check("signal on archived -> active, archived_at cleared (un-archive is a write)",
              r["status"] == "active" and r["archived_at"] is None and r["relevant"] is True, r)

        # ── three states, no fourth (rev 20) ─────────────────────────────────
        # A second active session; b goes dormant then reactivates by signal.
        await svc.apply_event(U, "sess-b", "UserPromptSubmit", cwd="/w/beta", machine="m1")
        await svc.apply_event(U, "sess-b", "SessionEnd")
        r = await svc.apply_event(U, "sess-b", "Stop")
        check("signal after dormant -> active (the one recovery rule, no special cases)",
              r["status"] == "active", r)

        # A crashed session keeps status='active' — the accepted known gap:
        # nothing observes or infers it back to dormant (repair mechanism deferred).
        await svc.apply_event(U, "sess-d", "UserPromptSubmit", cwd="/w/delta", machine="m1")
        s = await db.get(LedgerSession, "sess-d")
        check("crashed-active stays active (no inference — known gap)",
              s.status == "active" and s.turn_state == "processing")

        # ── batch archive: dormant only, keep-list honored ───────────────────
        await svc.apply_event(U, "sess-e", "UserPromptSubmit", cwd="/w/eps", machine="m1")
        await svc.apply_event(U, "sess-e", "SessionEnd")
        await svc.apply_event(U, "sess-f", "UserPromptSubmit", cwd="/w/zeta", machine="m1")
        await svc.apply_event(U, "sess-f", "SessionEnd")
        out = await svc.archive_batch(U, all_=True, keep=["sess-e"])
        ids = {r["id"] for r in out}
        check("batch archive: skips active + kept, archives the rest of the inactive",
              "sess-f" in ids and "sess-e" not in ids and "sess-d" not in ids, ids)

        # ── list ?status= filters the stored column ──────────────────────────
        items = await svc.list(U, status="active")
        check("list(status=active) returns only stored-active rows",
              all(r["status"] == "active" for r in items) and len(items) >= 2,
              [(r["id"], r["status"]) for r in items])

        # ── board ordering guarantee ─────────────────────────────────────────
        # Active: sess-a, sess-b, sess-d (first_seen asc = creation order).
        # Inactive: sess-e (dormant; f archived, c expired) after all actives.
        board = await svc.board(U)
        order = [r["id"] for r in board["sessions"]]
        actives = [r["id"] for r in board["sessions"] if r["status"] == "active"]
        check("board: active first in first_seen order, then inactive",
              actives == ["sess-a", "sess-b", "sess-d"] and order[-1] == "sess-e"
              and len(order) == 4, order)

        # Activity churn must not reorder the active cards.
        await svc.apply_event(U, "sess-b", "UserPromptSubmit")
        await svc.apply_event(U, "sess-a", "Stop")
        board = await svc.board(U)
        actives = [r["id"] for r in board["sessions"] if r["status"] == "active"]
        check("board: prompt/stop churn does not move active cards",
              actives == ["sess-a", "sess-b", "sess-d"], actives)

        # ── label is first-write-wins; workspace keeps refreshing ────────────
        # A card must not rename itself mid-life when the shell cd's deeper.
        # (Last, so the new session does not perturb the board assertions.)
        await svc.apply_event(U, "sess-g", "SessionStart", cwd="/w/gamma", machine="m1")
        first_label = (await db.get(LedgerSession, "sess-g")).label
        await svc.apply_event(U, "sess-g", "UserPromptSubmit", cwd="/w/gamma/skills/ledger")
        s = await db.get(LedgerSession, "sess-g")
        check("label settles on first sight, survives a cd into a subdirectory",
              first_label == "gamma·sess-g" and s.label == first_label,
              (first_label, s.label))
        check("workspace_id still refreshes to the current cwd",
              s.workspace_id == "/w/gamma/skills/ledger", s.workspace_id)

    await engine.dispose()
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


sys.exit(0 if asyncio.run(main()) else 1)
