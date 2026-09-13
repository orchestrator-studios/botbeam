"""Record-plane tests for LedgerService (Ledger Book rev 19, phase 2).

Drives the real service against in-memory SQLite (aiosqlite, test-only dep):
the atomic log_event composite (event + emitter liveness + stream update),
every validation rejection, create_stream, stream PUT/close semantics,
staleness, attribution (invariant 6), search,
the orientation index, the board payload, and reset across all three stores.
Run directly: venv/Scripts/python tests/test_ledger_record.py
"""
import asyncio
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models import LedgerSession, LedgerStream, LedgerEvent, LedgerRun, LedgerDeliverable
from services.ledger_service import LedgerService, LedgerError, NotFound, Conflict

RESULTS: list[bool] = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS" if ok else f"FAIL {detail}"), "-", name)


async def rejects(name, exc_type, coro):
    try:
        await coro
        check(name, False, "no exception")
    except exc_type:
        check(name, True)
    except Exception as e:  # noqa: BLE001 — wrong type is a failure, not a crash
        check(name, False, f"wrong exception {type(e).__name__}: {e}")


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def main():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        for t in (LedgerSession.__table__, LedgerStream.__table__, LedgerEvent.__table__, LedgerDeliverable.__table__, LedgerRun.__table__):
            await conn.run_sync(t.create)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        svc = LedgerService(db)
        U = 1

        # A live session to emit from.
        await svc.apply_event(U, "sess-a", "UserPromptSubmit", cwd="C:\\code\\botbeam", machine="m1")
        await svc.apply_event(U, "sess-a", "Stop")

        # ── log_event: the atomic composite ──────────────────────────────────
        out = await svc.log_event(
            U, stream_id="alpha", headline="Shipped the thing",
            body=["commit abc123", "deployed"], session_id="sess-a",
            create_stream={"title": "Alpha work", "working_paths": ["C:\\code\\alpha"]},
            stream_update={"state": "shipped v1", "next_action": "monitor"},
        )
        check("log_event returns {event, session, stream}",
              out["event"]["headline"] == "Shipped the thing"
              and out["session"]["id"] == "sess-a"
              and out["stream"]["id"] == "alpha", out)
        check("create_stream landed title + working_paths + update fields",
              out["stream"]["title"] == "Alpha work"
              and out["stream"]["state"] == "shipped v1"
              and out["stream"]["next_action"] == "monitor", out["stream"])
        check("emitting wrote liveness, turn_state untouched (invariant 9)",
              out["session"]["status"] == "active"
              and out["session"]["turn_state"] == "waiting", out["session"])
        check("attribution went live: session's stream_id = alpha",
              out["session"]["stream_id"] == "alpha", out["session"])

        # Liveness un-archives: end + archive, then log from it.
        await svc.apply_event(U, "sess-a", "SessionEnd")
        await svc.archive(U, "sess-a")
        out = await svc.log_event(U, stream_id="alpha", headline="Logged while archived",
                                  body=["x"], session_id="sess-a")
        check("log_event un-archives the emitter (status active, archived_at null)",
              out["session"]["status"] == "active"
              and out["session"]["archived_at"] is None, out["session"])

        # ── validations — and nothing partial persists ────────────────────────
        n_ev = await count(db, LedgerEvent)
        await rejects("empty headline -> 422", LedgerError,
                      svc.log_event(U, "alpha", "  ", ["x"], "sess-a"))
        await rejects("multi-line headline -> 422", LedgerError,
                      svc.log_event(U, "alpha", "a\nb", ["x"], "sess-a"))
        await rejects("0 bullets -> 422", LedgerError,
                      svc.log_event(U, "alpha", "ok", [], "sess-a"))
        await rejects("5 bullets -> 422", LedgerError,
                      svc.log_event(U, "alpha", "ok", ["1", "2", "3", "4", "5"], "sess-a"))
        await rejects("missing session_id -> 422", LedgerError,
                      svc.log_event(U, "alpha", "ok", ["x"], ""))
        await rejects("unknown session -> 404", NotFound,
                      svc.log_event(U, "alpha", "ok", ["x"], "nope"))
        await rejects("unknown stream without create_stream -> 404", NotFound,
                      svc.log_event(U, "ghost", "ok", ["x"], "sess-a"))
        await rejects("bad slug -> 422", LedgerError,
                      svc.log_event(U, "Not A Slug!", "ok", ["x"], "sess-a"))
        await rejects("unknown stream_update field -> 422", LedgerError,
                      svc.log_event(U, "alpha", "ok", ["x"], "sess-a",
                                    stream_update={"bogus": 1}))
        await db.rollback()
        check("failed calls left no partial rows (atomicity)",
              await count(db, LedgerEvent) == n_ev)

        # ── no built-in stream: "meta" is a slug like any other ──────────────
        await rejects('"meta" without create_stream -> 404 (nothing is built in)',
                      NotFound, svc.log_event(U, "meta", "Ledger work logged", ["x"], "sess-a"))
        out = await svc.log_event(U, "meta", "Ledger work logged", ["x"], "sess-a",
                                  create_stream={"title": "Ledger system"})
        check('"meta" created explicitly like any stream',
              out["stream"]["id"] == "meta")

        # ── attribution rule (invariant 6) ───────────────────────────────────
        rep = await svc.list(U)
        a = next(r for r in rep if r["id"] == "sess-a")
        check("every event attributes — meta included (now meta)",
              a["stream_id"] == "meta", a)
        await svc.log_event(U, "beta", "Beta shipped", ["y"], "sess-a",
                            create_stream={"title": "Beta"})
        a = (await svc.list(U, stream_id="beta"))
        check("most recent event wins (now beta) + ?stream_id filter",
              len(a) == 1 and a[0]["id"] == "sess-a", a)

        # Fallback: no events -> working_paths match; else None.
        await svc.apply_event(U, "sess-b", "UserPromptSubmit", cwd="C:\\code\\alpha", machine="m1")
        await svc.apply_event(U, "sess-c", "UserPromptSubmit", cwd="C:\\code\\elsewhere", machine="m1")
        rep = {r["id"]: r for r in await svc.list(U)}
        check("no events + working_paths match -> path attribution",
              rep["sess-b"]["stream_id"] == "alpha", rep["sess-b"])
        check("no events + no match -> stream_id null",
              rep["sess-c"]["stream_id"] is None, rep["sess-c"])

        # ── streams: PUT / close / staleness ─────────────────────────────────
        st = await svc.stream_put(U, "gamma", {"title": "Gamma", "open_loops": ["loop1"]})
        check("PUT creates a stream", st["title"] == "Gamma" and st["staleness"] == "fresh", st)
        st = await svc.stream_put(U, "gamma", {"state": "underway"})
        check("PUT replaces only given fields",
              st["title"] == "Gamma" and st["state"] == "underway", st)
        st = await svc.stream_put(U, "gamma", {"next_action": None})
        check("explicit null clears a field", st["next_action"] is None, st)
        await rejects("PUT unknown field -> 422", LedgerError,
                      svc.stream_put(U, "gamma", {"nope": 1}))

        row = (await db.execute(select(LedgerStream).where(
            LedgerStream.user_id == U, LedgerStream.id == "gamma"))).scalar_one()
        row.updated = datetime.utcnow() - timedelta(days=7)
        await db.commit()
        check("staleness: aging at 7d", svc.staleness(row) == "aging")
        row.updated = datetime.utcnow() - timedelta(days=20)
        await db.commit()
        check("staleness: stale at 20d", svc.staleness(row) == "stale")

        # Emitter is required with no exceptions (rev 19 ruling).
        await rejects("close without session_id -> 422", LedgerError,
                      svc.stream_close(U, "gamma", "done", ""))
        await rejects("close with unknown session -> 404", NotFound,
                      svc.stream_close(U, "gamma", "done", "nope"))
        await db.rollback()

        # Emitter liveness on close: end the session first, closing revives it.
        await svc.apply_event(U, "sess-a", "SessionEnd")
        n_ev = await count(db, LedgerEvent)
        out = await svc.stream_close(U, "gamma", "work done", session_id="sess-a")
        check("close sets closed_at + logs the closure event (one transaction)",
              out["stream"]["closed_at"] is not None
              and out["closure_event"]["stream_id"] == "gamma"
              and out["closure_event"]["session_id"] == "sess-a"
              and await count(db, LedgerEvent) == n_ev + 1, out)
        s_row = (await db.execute(select(LedgerSession).where(
            LedgerSession.id == "sess-a"))).scalar_one()
        check("close writes the emitter's liveness (invariant 9)",
              s_row.status == "active", s_row.status)
        check("closed stream: staleness null", out["stream"]["staleness"] is None)
        await rejects("re-close -> 409", Conflict, svc.stream_close(U, "gamma", "again", "sess-a"))
        await rejects("log to closed stream -> 409", Conflict,
                      svc.log_event(U, "gamma", "late", ["x"], "sess-a"))
        await db.rollback()
        await rejects("PUT closed stream -> 409", Conflict,
                      svc.stream_put(U, "gamma", {"state": "zombie"}))
        await db.rollback()

        lst = await svc.streams_list(U, status="active")
        check("streams_list(active) excludes closed",
              all(r["id"] != "gamma" for r in lst), [r["id"] for r in lst])
        lst = await svc.streams_list(U, status="closed")
        check("streams_list(closed) has gamma",
              [r["id"] for r in lst] == ["gamma"], lst)

        # ── events_list filters ──────────────────────────────────────────────
        items = await svc.events_list(U, stream_id="alpha")
        check("events_list ?stream_id", all(e["stream_id"] == "alpha" for e in items) and items)
        items = await svc.events_list(U, session_id="sess-a", limit=2)
        check("events_list ?session_id + limit, newest first",
              len(items) == 2 and items[0]["at"] >= items[1]["at"], items)

        # ── search ───────────────────────────────────────────────────────────
        hits = await svc.search(U, "beta")
        kinds = {(h["kind"], h["score"]) for h in hits}
        check("search hits event headline and stream title at 1.0",
              ("event", 1.0) in kinds and ("stream", 1.0) in kinds, kinds)
        hits = await svc.search(U, "underway")
        check("search hits stream state at 0.6",
              any(h["kind"] == "stream" and h["score"] == 0.6 for h in hits), hits)
        await rejects("empty q -> 422", LedgerError, svc.search(U, "  "))

        # ── index ────────────────────────────────────────────────────────────
        md = await svc.index_md(U)
        check("index: active streams with state/next + recent activity",
              "Alpha work" in md and "Beta shipped" in md and "## Recent activity" in md, md)
        check("index: no stream excluded — meta present, closed gamma absent",
              "Ledger system" in md and "Gamma" not in md, md)

        out = await svc.stream_close(U, "meta", "ordinary streams close", "sess-a")
        check("meta closes like any other stream",
              out["stream"]["closed_at"] is not None, out)

        # ── board ────────────────────────────────────────────────────────────
        b = await svc.board(U)
        check("board carries events (newest first) and active streams, no products",
              "products" not in b and b["events"]
              and b["events"][0]["at"] >= b["events"][-1]["at"]
              and any(s["id"] == "alpha" for s in b["streams"]), list(b.keys()))
        actives = [r["id"] for r in b["sessions"] if r["status"] == "active"]
        check("board: session ordering guarantee intact (first_seen asc)",
              actives == ["sess-a", "sess-b", "sess-c"], actives)
        check("board hides closed-stream events (meta closed above), keeps open alpha's",
              all(e["stream_id"] != "meta" for e in b["events"])
              and any(e["stream_id"] == "alpha" for e in b["events"]), b["events"])
        md = await svc.index_md(U)
        check("index recent activity hides closed streams too",
              "Ledger work logged" not in md and "Alpha work" in md, md)
        check("data endpoint still serves the closed stream's history",
              any(e["stream_id"] == "meta" for e in await svc.events_list(U)))

        # ── reset clears all three stores ────────────────────────────────────
        await svc.reset(U)
        check("reset truncates sessions + events + streams",
              await count(db, LedgerSession) == 0
              and await count(db, LedgerEvent) == 0
              and await count(db, LedgerStream) == 0)

    await engine.dispose()
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


sys.exit(0 if asyncio.run(main()) else 1)
