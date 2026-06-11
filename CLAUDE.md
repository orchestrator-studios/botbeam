# BotBeam — repo guide

Virtual display & beam surface for **orchestra**. **FastAPI + async SQLAlchemy (MySQL)** backend, **React 19 + Vite + TS** frontend. Auth matches the house pattern (`kh` / `table-that`): **JWT HS256 + bcrypt + org/role**, one bearer-token credential for browser and agent alike.

## Run
- **Backend:** `cd backend && venv/Scripts/python -m uvicorn main:app --port 4888` (needs `.env` — see `.env.example`; deps in `requirements.txt`).
- **Frontend:** `cd frontend && npm run build` (served by the backend at `/`) or `npm run dev` (:5173).

## Key files
- `backend/main.py` — app wiring: CORS, routers, `/ws`, startup (create tables + seed Default Org), serves the built frontend.
- `backend/config/settings.py` — env-driven settings (DB, JWT).
- `backend/database.py` — async engine/session (`mysql+aiomysql`), `get_async_db`, `init_async_db`.
- `backend/models.py` — `Organization`, `User` (int PK, `userrole` enum), `Device` (a user-scoped display tab; names unique per user, one undeletable default display per user, archivable).
- `backend/schemas.py` — domain objects only (`User`, `Device`, `DeviceContent`, `DeviceSummary`, `DeviceKind`/`ContentType` Literals); mirrors `frontend/src/types/index.ts` name-for-name in the same order. Endpoint-specific request/response wrappers live in the routers (backend) and `frontend/src/lib/api/botbeamApi.ts` (frontend).
- `backend/services/auth_service.py` — JWT create/verify + `get_current_user` dependency.
- `backend/services/user_service.py` — user/org CRUD (bcrypt via passlib).
- `backend/services/device_service.py` — the three beams (`beam_default` / `beam_new` 409-on-dup / `beam_existing` 404-on-miss) + clear/rename/archive/unarchive/delete/reset + content validation (9 content types, 500 KB cap — the canonical list is `ContentType` in `backend/schemas.py`). Agents address the default display via the reserved `default` path segment; `list?view=summary` returns no bodies.
- `backend/routers/auth.py` → `/auth/*` · `backend/routers/devices.py` → `/api/devices`.
- `backend/websocket.py` — per-user WS channels for live updates.
- `backend/config/logging_config.py` + `backend/middleware/logging_middleware.py` — house logging (kh / table-that pattern): console + daily-rotating file (`LOG_FORMAT=json` for structured file logs), per-request id via ContextVar, timing with SLOW/4xx/5xx levels. Modules log under `botbeam.*` loggers; routers/services log sparsely — security events (login failures, agent tokens) and state changes at info, per-beam content writes at debug.

## Auth model
One credential: a JWT bearer. The browser keeps it in `localStorage`; the agent (orchestra `botbeam` skill) keeps a long-lived one in `~/.config/orchestra/botbeam.json`. Devices are scoped to the authenticated user. **No secrets in the repo.**

## Notes
- DB is MySQL; tables auto-create on startup (no Alembic yet).
- Replaced the original Node/Express + MCP `signal` prototype (kept at `github.com/cliff-rosen/signal`). MCP was dropped — orchestra calls the REST API via a bundled Python skill, so there's no MCP server here.
- Deploy (Copilot/ECS or EB) is not yet set up — that's a follow-up.
