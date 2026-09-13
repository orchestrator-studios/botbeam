"""Runs + deliverables tests (Ledger Book rev 21, invariant 10).

A run is declared at both ends; the ⚡ is a join on ended_at IS NULL, never a
window. Deliverables are born only inside runs, advanced only by closing runs,
and retired only by the user. Drives the real service on in-memory SQLite.
Run directly: venv/Scripts/python tests/test_ledger_runs.py
"""
import asyncio
import sys

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
    except Exception as e:  # noqa: BLE001
        check(name, False, f"wrong exception {type(e).__name__}: {e}")


async def main():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        for t in (LedgerSession.__table__, LedgerStream.__table__, LedgerEvent.__table__,
                  LedgerDeliverable.__table__, LedgerRun.__table__):
            await conn.run_sync(t.create)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        svc = LedgerService(db)
        U = 1
        await svc.apply_event(U, "sess-a", "UserPromptSubmit", cwd="C:\\code\\botbeam", machine="m1")
        await svc.apply_event(U, "sess-b", "UserPromptSubmit", cwd="C:\\code\\other", machine="m1")

        # The deliverable's stream must exist first — nothing is built in.
        await svc.stream_put(U, "meta", {"title": "Ledger system"})

        # ── open: mint the deliverable in the same call ──────────────────────
        out = await svc.run_open(
            U, "sess-a", "cutting rev 21",
            create_deliverable={"name": "The Ledger Book", "home": "C:\\code\\woodshed\\docs\\ledger\\ledger-reference.html", "stream_id": "meta"})
        run1, dl = out["run"], out["deliverable"]
        check("open mints run + deliverable, 3-part response",
              run1["ended_at"] is None and run1["outcome"] is None
              and dl["name"] == "The Ledger Book" and dl["status"] == "live"
              and dl["stream_id"] == "meta", out)
        check("open_run join on the session: id/intent/deliverable_id+name/started_at",
              out["session"]["open_run"]["id"] == run1["id"]
              and out["session"]["open_run"]["intent"] == "cutting rev 21"
              and out["session"]["open_run"]["deliverable_id"] == dl["id"]
              and out["session"]["open_run"]["deliverable_name"] == "The Ledger Book"
              and out["session"]["open_run"]["started_at"], out["session"]["open_run"])

        # ring+⚡: Stop mid-run — activity waiting, bolt stays (all four combos legal)
        r = await svc.apply_event(U, "sess-a", "Stop")
        check("ring+bolt: waiting with an open run (work parked mid-run)",
              r["activity"] == "waiting" and r["open_run"] is not None, r)

        # ── one open run per session ─────────────────────────────────────────
        await rejects("second open on the same session -> 409", Conflict,
                      svc.run_open(U, "sess-a", "something else", deliverable_id=dl["id"]))
        await db.rollback()

        # ── open validations ─────────────────────────────────────────────────
        await rejects("missing intent -> 422", LedgerError,
                      svc.run_open(U, "sess-b", "  ", deliverable_id=dl["id"]))
        await rejects("neither deliverable_id nor create_deliverable -> 422", LedgerError,
                      svc.run_open(U, "sess-b", "work"))
        await rejects("both deliverable_id and create_deliverable -> 422", LedgerError,
                      svc.run_open(U, "sess-b", "work", deliverable_id=dl["id"],
                                   create_deliverable={"name": "x", "home": "h", "stream_id": "meta"}))
        await rejects("create_deliverable missing home -> 422", LedgerError,
                      svc.run_open(U, "sess-b", "work",
                                   create_deliverable={"name": "x", "stream_id": "meta"}))
        await rejects("unknown deliverable_id -> 404", NotFound,
                      svc.run_open(U, "sess-b", "work", deliverable_id="dl_nope"))
        await rejects("unknown stream in create_deliverable -> 404 (no nested create)", NotFound,
                      svc.run_open(U, "sess-b", "work",
                                   create_deliverable={"name": "x", "home": "h", "stream_id": "ghost"}))
        await rejects("unknown session -> 404", NotFound,
                      svc.run_open(U, "nope", "work", deliverable_id=dl["id"]))
        await db.rollback()

        # ── close: state rules, deliverable advance, non-opener close ────────
        await rejects("close missing state on closed -> 422", LedgerError,
                      svc.run_close(U, run1["id"], "sess-a", "closed"))
        await rejects("close with state on abandoned -> 422", LedgerError,
                      svc.run_close(U, run1["id"], "sess-a", "abandoned", state="rev 21"))
        await rejects("bad outcome -> 422", LedgerError,
                      svc.run_close(U, run1["id"], "sess-a", "finished", state="x"))
        await db.rollback()

        # Non-opener close is ALLOWED (the crash-leak cleanup path) and writes
        # the CLOSER's liveness.
        await svc.apply_event(U, "sess-b", "SessionEnd")
        out = await svc.run_close(U, run1["id"], "sess-b", "closed", state="rev 21")
        check("closed: run ended, deliverable advanced (state, last_run_id, updated)",
              out["run"]["outcome"] == "closed" and out["run"]["ended_at"]
              and out["deliverable"]["state"] == "rev 21"
              and out["deliverable"]["last_run_id"] == run1["id"], out)
        check("non-opener close allowed; closer's liveness written",
              out["session"]["id"] == "sess-b" and out["session"]["status"] == "active", out["session"])
        await rejects("re-close -> 409", Conflict,
                      svc.run_close(U, run1["id"], "sess-a", "abandoned"))
        await db.rollback()

        # ── abandoned leaves the deliverable untouched ───────────────────────
        out = await svc.run_open(U, "sess-a", "a dead end", deliverable_id=dl["id"])
        run2 = out["run"]
        out = await svc.run_close(U, run2["id"], "sess-a", "abandoned")
        check("abandoned: run ended, deliverable untouched",
              out["run"]["outcome"] == "abandoned"
              and out["deliverable"]["state"] == "rev 21"
              and out["deliverable"]["last_run_id"] == run1["id"], out)

        # ── retire / unretire — the user's call ──────────────────────────────
        out = await svc.run_open(U, "sess-a", "more work", deliverable_id=dl["id"])
        run3 = out["run"]
        await rejects("retire with an open run -> 409", Conflict,
                      svc.deliverable_set_status(U, dl["id"], retired=True))
        await db.rollback()
        await svc.run_close(U, run3["id"], "sess-a", "closed", state="rev 21 final")
        d = await svc.deliverable_set_status(U, dl["id"], retired=True)
        check("retire after close -> retired", d["status"] == "retired", d)
        await rejects("open on a retired deliverable -> 409", Conflict,
                      svc.run_open(U, "sess-a", "necromancy", deliverable_id=dl["id"]))
        await db.rollback()
        d = await svc.deliverable_set_status(U, dl["id"], retired=False)
        check("unretire -> live again", d["status"] == "live", d)

        # ── recovery recipe: leaked run -> list open -> abandon -> open new ──
        out = await svc.run_open(U, "sess-b", "will crash", deliverable_id=dl["id"])
        leaked = out["run"]["id"]
        open_runs = await svc.runs_list(U, open_only=True, session_id="sess-b")
        check("runs?open=true&session_id finds the leaked run",
              [r["id"] for r in open_runs] == [leaked], open_runs)
        await svc.run_close(U, leaked, "sess-b", "abandoned")
        out = await svc.run_open(U, "sess-b", "fresh start", deliverable_id=dl["id"])
        check("after abandoning the leak, a new run opens", out["run"]["ended_at"] is None)
        await svc.run_close(U, out["run"]["id"], "sess-b", "abandoned")

        # ── lists ────────────────────────────────────────────────────────────
        allruns = await svc.runs_list(U)
        check("runs list newest-first with elapsed_s",
              len(allruns) == 5 and all("elapsed_s" in r for r in allruns)
              and allruns[0]["started_at"] >= allruns[-1]["started_at"], len(allruns))
        check("runs ?open=true empty when nothing is open",
              await svc.runs_list(U, open_only=True) == [])
        dls = await svc.deliverables_list(U, status="live")
        check("deliverables list: live filter + stream filter",
              [x["id"] for x in dls] == [dl["id"]]
              and (await svc.deliverables_list(U, stream_id="ghost")) == [], dls)

        # ── search + board carry the new objects ─────────────────────────────
        hits = await svc.search(U, "ledger book")
        check("search finds the deliverable by name",
              any(h["kind"] == "deliverable" and h["score"] == 1.0 for h in hits), hits)
        await svc.run_open(U, "sess-a", "board check", deliverable_id=dl["id"])
        board = await svc.board(U)
        a = next(r for r in board["sessions"] if r["id"] == "sess-a")
        check("board session carries open_run (the bolt is a join)",
              a["open_run"] is not None and a["open_run"]["intent"] == "board check", a["open_run"])
        check("board lists the deliverable (its stream is open)",
              any(x["id"] == dl["id"] for x in board["deliverables"]), board["deliverables"])

        # ── the board invariant: a closed stream takes its things with it ────
        await svc.run_close(U, a["open_run"]["id"], "sess-a", "abandoned")
        await svc.stream_close(U, "meta", "board invariant check", "sess-a")
        board = await svc.board(U)
        check("closed stream takes its deliverables and events off the board",
              all(x["stream_id"] != "meta" for x in board["deliverables"])
              and all(e["stream_id"] != "meta" for e in board["events"]), board["deliverables"])
        check("data endpoints still serve the closed stream's deliverable",
              any(x["id"] == dl["id"] for x in await svc.deliverables_list(U, status="live")))

        # ── reset clears all five stores ─────────────────────────────────────
        await svc.reset(U)
        for model in (LedgerRun, LedgerDeliverable, LedgerEvent, LedgerStream, LedgerSession):
            n = (await db.execute(select(func.count()).select_from(model))).scalar()
            if n:
                check(f"reset cleared {model.__tablename__}", False, n)
                break
        else:
            check("reset truncates all five stores", True)

    await engine.dispose()
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    return all(RESULTS)


sys.exit(0 if asyncio.run(main()) else 1)
