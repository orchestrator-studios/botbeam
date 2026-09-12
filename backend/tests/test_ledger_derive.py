"""Cheat-sheet cascade tests for LedgerService.derive — pure, no DB."""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from models import LedgerSession
from services.ledger_service import LedgerService
from config.settings import settings

NOW = datetime(2026, 9, 12, 12, 0, 0)
SIL = timedelta(minutes=settings.LEDGER_SILENCE_WINDOW_MINUTES)
RUN = timedelta(seconds=settings.LEDGER_RUN_WINDOW_SECONDS)


def s(**kw):
    base = dict(
        id="abc123", user_id=1, first_seen=NOW - timedelta(hours=2),
        turn_state="waiting",
        last_event_at=NOW - timedelta(seconds=5), last_prompt_at=None,
        last_stop_at=None, last_run_at=None, ended_at=None,
        ever_prompted=True, archived_at=None, transcript_missing_since=None,
        sweep_miss_count=0,
    )
    base.update(kw)
    return LedgerSession(**base)


def check(name, sess, status, activity, relevant):
    d = LedgerService.derive(sess, NOW)
    ok = d == {"status": status, "activity": activity, "relevant": relevant}
    print(("PASS" if ok else f"FAIL {d}"), "-", name)
    return ok


results = [
    # T2: ghost gate — launched, never prompted
    check("never prompted -> not relevant", s(ever_prompted=False),
          "active", "waiting", False),
    # T3: prompt signal stored turn_state=processing
    check("turn_state processing -> processing",
          s(turn_state="processing", last_prompt_at=NOW - timedelta(seconds=10)),
          "active", "processing", True),
    # T4a: tool burst -> run
    check("mutation within run window -> run",
          s(turn_state="processing", last_prompt_at=NOW - timedelta(seconds=30), last_run_at=NOW - timedelta(seconds=5)),
          "active", "run", True),
    # T4b: bolt decays
    check("mutation past run window -> processing",
          s(turn_state="processing", last_prompt_at=NOW - timedelta(minutes=5),
            last_run_at=NOW - RUN - timedelta(seconds=1),
            last_event_at=NOW - timedelta(minutes=1)),
          "active", "processing", True),
    # T4c: Stop stored turn_state=waiting — run bolt does NOT show while waiting
    check("turn_state waiting -> waiting even with recent mutation",
          s(turn_state="waiting", last_prompt_at=NOW - timedelta(minutes=2),
            last_stop_at=NOW - timedelta(minutes=1), last_run_at=NOW - timedelta(seconds=5)),
          "active", "waiting", True),
    # T5a: clean exit -> dormant immediately
    check("SessionEnd -> dormant immediately",
          s(ended_at=NOW - timedelta(seconds=3), last_event_at=NOW - timedelta(seconds=3)),
          "dormant", None, True),
    # T5b/c: crash or idle -> dormant after silence window
    check("silence past window -> dormant",
          s(last_event_at=NOW - SIL - timedelta(seconds=1), last_prompt_at=NOW - SIL - timedelta(seconds=2)),
          "dormant", None, True),
    check("silence within window, waiting -> still active",
          s(last_event_at=NOW - SIL + timedelta(minutes=1), last_stop_at=NOW - SIL + timedelta(minutes=1)),
          "active", "waiting", True),
    # T6: archived, no event since -> hidden
    check("archived, no event since -> archived/hidden",
          s(archived_at=NOW - timedelta(minutes=5), last_event_at=NOW - timedelta(minutes=5)),
          "archived", None, False),
    # T8: event after archived_at -> back (derived un-archive)
    check("event after archive -> derived un-archive",
          s(turn_state="processing", archived_at=NOW - timedelta(minutes=5),
            last_event_at=NOW - timedelta(seconds=2), last_prompt_at=NOW - timedelta(seconds=2)),
          "active", "processing", True),
    # crash cleanup precondition: dormant hides turn_state regardless
    check("dormant with stale processing -> activity None",
          s(turn_state="processing", last_event_at=NOW - SIL - timedelta(minutes=1)),
          "dormant", None, True),
    # T9: expired
    check("missing x3 sweeps, no event since -> expired",
          s(sweep_miss_count=3, transcript_missing_since=NOW - timedelta(minutes=20),
            last_event_at=NOW - timedelta(minutes=25)),
          "expired", None, False),
    check("missing x2 only -> not expired (dormant via silence)",
          s(sweep_miss_count=2, transcript_missing_since=NOW - timedelta(minutes=20),
            last_event_at=NOW - timedelta(minutes=25)),
          "dormant", None, True),
    # resume after clean exit
    check("event after ended_at -> reopened",
          s(ended_at=NOW - timedelta(hours=1), last_event_at=NOW - timedelta(seconds=4),
            last_stop_at=NOW - timedelta(seconds=4)),
          "active", "waiting", True),
]

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
