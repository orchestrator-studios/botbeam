"""Router-level tests for /ledger (Ledger Book rev 19) — the wire contract.

Covers what the service tests can't: the /signals rename with its deprecated
/events alias (both spellings must work during the hook cutover), the 201 on
POST /ledger/events, the 422 on a `product` block (extra=forbid), the
text/markdown index, and error-shape mapping. Runs FastAPI's TestClient over a
throwaway app with in-memory SQLite and a stubbed current user (httpx +
aiosqlite, test-only deps). Run: venv/Scripts/python tests/test_ledger_router.py
"""
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models import LedgerSession, LedgerStream, LedgerEvent
from routers import ledger
from services.auth_service import get_current_user
from database import get_async_db

RESULTS: list[bool] = []


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(("PASS" if ok else f"FAIL {detail}"), "-", name)


class FakeUser:
    user_id = 1


engine = create_async_engine("sqlite+aiosqlite://")
Session = async_sessionmaker(engine, expire_on_commit=False)


async def override_db():
    async with Session() as s:
        yield s


app = FastAPI()
app.include_router(ledger.router, prefix="/ledger")
app.dependency_overrides[get_current_user] = lambda: FakeUser()
app.dependency_overrides[get_async_db] = override_db


async def make_tables():
    async with engine.begin() as conn:
        for t in (LedgerSession.__table__, LedgerStream.__table__, LedgerEvent.__table__):
            await conn.run_sync(t.create)

import asyncio
asyncio.run(make_tables())

c = TestClient(app)

# ── signals: new spelling ─────────────────────────────────────────────────────
r = c.post("/ledger/sessions/s1/signals",
           json={"signal": "UserPromptSubmit", "cwd": "C:\\code\\x", "machine": "m1"})
check("POST /signals with 'signal' field -> 200, processing",
      r.status_code == 200 and r.json()["turn_state"] == "processing", r.text)

# ── signals: deprecated alias, old field ─────────────────────────────────────
r = c.post("/ledger/sessions/s1/events", json={"event": "Stop"})
check("POST /events alias with 'event' field -> 200, waiting",
      r.status_code == 200 and r.json()["turn_state"] == "waiting", r.text)

# Mixed spellings also work (new path, old field and vice versa).
r = c.post("/ledger/sessions/s1/signals", json={"event": "Stop"})
r2 = c.post("/ledger/sessions/s1/events", json={"signal": "Stop"})
check("mixed path/field spellings accepted during cutover",
      r.status_code == 200 and r2.status_code == 200, (r.text, r2.text))

r = c.post("/ledger/sessions/s1/signals", json={"cwd": "C:\\x"})
check("neither signal nor event -> 422", r.status_code == 422, r.text)
r = c.post("/ledger/sessions/s1/signals", json={"signal": "Bogus"})
check("unknown signal value -> 422", r.status_code == 422, r.text)

# ── record plane over the wire ───────────────────────────────────────────────
r = c.post("/ledger/events", json={
    "stream_id": "alpha", "headline": "Shipped it", "body": ["done"],
    "session_id": "s1", "create_stream": {"title": "Alpha"}})
check("POST /ledger/events -> 201 {event, session, stream}",
      r.status_code == 201 and set(r.json()) == {"event", "session", "stream"}, r.text)

r = c.post("/ledger/events", json={
    "stream_id": "alpha", "headline": "With product", "body": ["x"],
    "session_id": "s1", "product": {"name": "n", "home": "h"}})
check("product block -> 422 (deferred)", r.status_code == 422, r.text)

r = c.post("/ledger/events", json={
    "stream_id": "ghost", "headline": "No stream", "body": ["x"], "session_id": "s1"})
check("unknown stream -> 404 {error:not_found}",
      r.status_code == 404 and r.json()["detail"]["error"] == "not_found", r.text)

r = c.post("/ledger/streams/alpha/close", json={"reason": "done", "session_id": "s1"})
check("close -> 200 {stream, closure_event}",
      r.status_code == 200 and set(r.json()) == {"stream", "closure_event"}, r.text)
r = c.post("/ledger/streams/alpha/close", json={"reason": "again"})
check("re-close -> 409 {error:conflict}",
      r.status_code == 409 and r.json()["detail"]["error"] == "conflict", r.text)

r = c.get("/ledger/index")
check("GET /ledger/index -> text/markdown",
      r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
      and "Recent activity" in r.text, r.headers.get("content-type"))

r = c.get("/ledger/board")
b = r.json()
check("GET /ledger/board carries sessions+events+streams, no products",
      r.status_code == 200 and set(b) == {"sessions", "events", "streams", "as_of"}, list(b))

r = c.get("/ledger/search", params={"q": "shipped"})
check("GET /ledger/search finds the event",
      r.status_code == 200 and any(h["kind"] == "event" for h in r.json()["items"]), r.text)

print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
sys.exit(0 if all(RESULTS) else 1)
