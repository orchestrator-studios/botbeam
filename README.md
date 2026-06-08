# BotBeam

The **virtual display & beam surface for [orchestra](https://github.com/orchestrator-studios/orchestra)** — an agent *beams* content (dashboards, tables, markdown, lists, images, web views) to display tabs a user watches in the browser, live. The companion-UX surface of orchestra's auxiliary plane.

**Stack:** FastAPI + async SQLAlchemy (MySQL) backend · React 19 + Vite + TypeScript frontend. Auth is **JWT (HS256) + bcrypt + org/role** — the same pattern as `kh` and `table-that`.

## Run locally

### Backend — FastAPI on :4888
```bash
cd backend
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt    # macOS/Linux: venv/bin/pip
cp .env.example .env                                       # fill DB creds + JWT_SECRET_KEY
venv/Scripts/python -m uvicorn main:app --port 4888       # macOS/Linux: venv/bin/python
```
Tables are created on startup and a "Default Organization" is seeded.

### Frontend — React
```bash
cd frontend
npm install
npm run build      # the built app is served by the backend at /
# or: npm run dev  # hot-reload dev server on :5173 (talks to the backend via CORS)
```

Open **http://localhost:4888** → register, sign in, then **Mint a token** (Home) and drop it in `~/.config/orchestra/botbeam.json` to wire the orchestra `botbeam` skill.

## API (all device routes require `Authorization: Bearer <jwt>`)
- `POST /auth/register` · `POST /auth/login` → `{ access_token, token_type, user_id, org_id, role, email, username }`
- `GET /auth/me` · `POST /auth/agent-token` (long-lived token for the agent)
- `GET|POST /api/devices` · `PATCH|DELETE /api/devices/{id}` · `DELETE /api/devices` (reset)
- `WS /ws?token=<jwt>` — live display updates

## Layout
```
backend/   FastAPI app — config · models · database · schemas · services/ · routers/ · websocket · main
frontend/  React 19 + Vite + TypeScript
```

This replaces the original Node/Express + MCP prototype (`signal`); MCP was dropped — orchestra calls the REST API through a bundled Python skill.
