"""Per-user WebSocket channels for live display updates."""
import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger("botbeam.ws")


class WSManager:
    def __init__(self):
        self._channels: dict[int, set[WebSocket]] = {}
        # Concurrent REST mutations may broadcast to the same socket at once;
        # websockets raises on concurrent sends, so serialize them per-manager.
        self._send_lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        conns = self._channels.setdefault(user_id, set())
        conns.add(ws)
        logger.info("WS connected (user=%s, connections=%d)", user_id, len(conns))

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._channels.get(user_id)
        if conns:
            conns.discard(ws)
            logger.info("WS disconnected (user=%s, remaining=%d)", user_id, len(conns))
            if not conns:
                self._channels.pop(user_id, None)

    async def broadcast(self, user_id: int, message: dict) -> None:
        conns = list(self._channels.get(user_id, ()))
        logger.debug("WS broadcast %s (user=%s, recipients=%d)",
                     message.get("event"), user_id, len(conns))
        if not conns:
            return
        data = json.dumps(message)
        dead = []
        async with self._send_lock:
            for ws in conns:
                try:
                    await ws.send_text(data)
                except Exception as e:
                    logger.warning("WS send failed (user=%s): %s — pruning connection", user_id, e)
                    dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)


manager = WSManager()
