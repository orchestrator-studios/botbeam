from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from jose import jwt, JWTError

from config.settings import settings
from database import init_async_db, AsyncSessionLocal
from services.user_service import UserService
from routers import auth as auth_router, devices as devices_router, memories as memories_router, ledger as ledger_router
from websocket import manager
from config.logging_config import setup_logging
from middleware import LoggingMiddleware

logger = setup_logging()
logger.info("Logging configured (level=%s, format=%s, dir=%s)",
            settings.LOG_LEVEL, settings.LOG_FORMAT, settings.LOG_DIR)

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

# Per-request logging (request id, timing, status-based levels).
app.add_middleware(LoggingMiddleware)

# Bearer tokens (not cookies) → no credentialed CORS needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])
app.include_router(devices_router.router, prefix="/api", tags=["devices"])
app.include_router(memories_router.router, prefix="/api", tags=["memories"])
app.include_router(ledger_router.router, prefix="/ledger", tags=["ledger"])


@app.on_event("startup")
async def _startup():
    await init_async_db()
    async with AsyncSessionLocal() as db:
        await UserService(db).get_or_create_default_org()
    logger.info("BotBeam started — DB %s @ %s", settings.DB_NAME, settings.DB_HOST)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}


@app.get("/api/health")
async def api_health():
    return {"status": "ok", "version": settings.VERSION}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = payload.get("user_id")
        except JWTError:
            user_id = None
    if not user_id:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket, user_id)
    try:
        # Server-push only: clients never send. Parking on receive() keeps the
        # handler (and so the connection) alive until the client goes away.
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, user_id)


# ── Serve the built React frontend (single-process local demo) ──
_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/app", StaticFiles(directory=str(_dist)), name="app")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith(("api/", "auth/", "ws", "ledger/")):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index = _dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Frontend not built"}, status_code=404)


if __name__ == "__main__":
    # Canonical run: `python main.py` → always BotBeam's port (4888), with reload.
    # (Bare `uvicorn main:app` would default to 8000 and miss the frontend's API URL.)
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=settings.PORT, reload=True)
