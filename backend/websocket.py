"""Per-user WebSocket channels for live display updates."""
import json
from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self._channels: dict[int, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self._channels.setdefault(user_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._channels.get(user_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._channels.pop(user_id, None)

    async def broadcast(self, user_id: int, message: dict) -> None:
        conns = list(self._channels.get(user_id, ()))
        if not conns:
            return
        data = json.dumps(message)
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                pass


manager = WSManager()
