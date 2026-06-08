"""Device (display tab) CRUD + content validation — ported from signal's store.js.
Scoped by user_id."""
import json
import secrets
import string
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device

VALID_CONTENT_TYPES = {"text", "html", "url", "image", "markdown", "dashboard", "list", "table"}
MAX_BODY_BYTES = 512 * 1024  # 500KB
_ALPHABET = string.ascii_letters + string.digits


class ContentError(ValueError):
    """Invalid content — surfaced as a 400."""


def _gen_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


def validate_content(ctype: str, body) -> str:
    if not ctype or ctype not in VALID_CONTENT_TYPES:
        raise ContentError(f'Invalid content type "{ctype}". Must be one of: {", ".join(sorted(VALID_CONTENT_TYPES))}')
    if body is None:
        raise ContentError("Content body is required")
    body_str = body if isinstance(body, str) else json.dumps(body)

    if ctype == "table":
        try:
            parsed = json.loads(body_str)
        except json.JSONDecodeError:
            raise ContentError("Table body must be valid JSON")
        if isinstance(parsed, list):
            if not parsed or not isinstance(parsed[0], dict):
                raise ContentError("Table body must be a non-empty array of objects")
            cols = [{"id": k, "label": k} for k in parsed[0].keys()]
            body_str = json.dumps({"columns": cols, "rows": parsed})
        elif isinstance(parsed, dict):
            if not isinstance(parsed.get("columns"), list) or not isinstance(parsed.get("rows"), list):
                raise ContentError('Table body must have "columns" and "rows" arrays')
        else:
            raise ContentError("Table body must be a JSON array or {columns, rows} object")

    if len(body_str.encode("utf-8")) > MAX_BODY_BYTES:
        raise ContentError(f"Content body too large (max {MAX_BODY_BYTES // 1024}KB)")
    return body_str


def serialize(d: Device) -> dict:
    content = None
    if d.content_type:
        content = {
            "type": d.content_type,
            "body": d.content_body,
            "updatedAt": (d.content_updated_at.isoformat() + "Z") if d.content_updated_at else None,
        }
    return {
        "id": d.id,
        "name": d.name,
        "createdAt": (d.created_at.isoformat() + "Z") if d.created_at else None,
        "content": content,
    }


class DeviceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int) -> list[dict]:
        res = await self.db.execute(
            select(Device).where(Device.user_id == user_id).order_by(Device.created_at)
        )
        return [serialize(d) for d in res.scalars().all()]

    async def _get(self, user_id: int, device_id: str) -> Optional[Device]:
        res = await self.db.execute(
            select(Device).where(Device.user_id == user_id, Device.id == device_id)
        )
        return res.scalars().first()

    async def create(self, user_id: int, name: str, content: Optional[dict]) -> dict:
        if not name or not isinstance(name, str):
            raise ContentError("Device name is required")
        d = Device(id=_gen_id(), user_id=user_id, name=name)
        if content:
            d.content_type = content["type"]
            d.content_body = validate_content(content["type"], content.get("body"))
            d.content_updated_at = datetime.utcnow()
        self.db.add(d)
        await self.db.commit()
        await self.db.refresh(d)
        return serialize(d)

    async def update(
        self, user_id: int, device_id: str, *,
        name: Optional[str] = None, content_provided: bool = False, content: Optional[dict] = None,
    ) -> Optional[dict]:
        d = await self._get(user_id, device_id)
        if not d:
            return None
        if name is not None:
            d.name = name
        if content_provided:
            if content is None:
                d.content_type = None
                d.content_body = None
                d.content_updated_at = None
            else:
                d.content_type = content["type"]
                d.content_body = validate_content(content["type"], content.get("body"))
                d.content_updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(d)
        return serialize(d)

    async def delete(self, user_id: int, device_id: str) -> bool:
        d = await self._get(user_id, device_id)
        if not d:
            return False
        await self.db.delete(d)
        await self.db.commit()
        return True

    async def reset(self, user_id: int) -> None:
        await self.db.execute(delete(Device).where(Device.user_id == user_id))
        await self.db.commit()
