"""Device (display tab) operations + content validation.

The agent-facing model: every user has one default display (always exists,
never renamed/archived/deleted) plus named tabs. The three beams map to
distinct service calls — beam_default (upsert the default's content),
beam_new (create, name must be free), beam_existing (replace content by id).
Names are unique per user; the agent resolves spoken names to ids via list().
"""
import json
import secrets
import string
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device

VALID_CONTENT_TYPES = {"text", "html", "url", "image", "markdown", "dashboard", "list", "table"}
VALID_KINDS = {"display", "lockbox"}
MAX_BODY_BYTES = 512 * 1024  # 500KB
DEFAULT_DEVICE_NAME = "Main"
_ALPHABET = string.ascii_letters + string.digits


class ContentError(ValueError):
    """Invalid content — surfaced as a 400."""


class NameConflict(ValueError):
    """Device name already in use for this user — surfaced as a 409."""


class DefaultDeviceError(ValueError):
    """Operation not allowed on the default display — surfaced as a 403."""


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


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return (dt.isoformat() + "Z") if dt else None


def serialize(d: Device) -> dict:
    content = None
    if d.content_type:
        content = {
            "type": d.content_type,
            "body": d.content_body,
            "updatedAt": _iso(d.content_updated_at),
        }
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "kind": d.kind,
        "isDefault": bool(d.is_default),
        "archivedAt": _iso(d.archived_at),
        "createdAt": _iso(d.created_at),
        "content": content,
    }


def summarize(d: Device) -> dict:
    """Cheap listing for the agent: no content bodies (they can be 500KB each)."""
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "kind": d.kind,
        "isDefault": bool(d.is_default),
        "archivedAt": _iso(d.archived_at),
        "contentType": d.content_type,
        "contentUpdatedAt": _iso(d.content_updated_at),
        "createdAt": _iso(d.created_at),
    }


class DeviceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── reads ──

    async def list(
        self, user_id: int, archived: bool = False, summary: bool = False,
        kind: Optional[str] = None,
    ) -> list[dict]:
        """Active entries (default first) or, with archived=True, the archive.
        Optionally filter to one kind ('display' tabs or 'lockbox' stashes)."""
        if not archived:
            await self.get_or_create_default(user_id)
        conds = [
            Device.user_id == user_id,
            Device.archived_at.isnot(None) if archived else Device.archived_at.is_(None),
        ]
        if kind is not None:
            conds.append(Device.kind == kind)
        res = await self.db.execute(
            select(Device).where(*conds).order_by(Device.is_default.desc(), Device.created_at)
        )
        shape = summarize if summary else serialize
        return [shape(d) for d in res.scalars().all()]

    async def get(self, user_id: int, device_id: str) -> Optional[dict]:
        d = await self._get(user_id, device_id)
        return serialize(d) if d else None

    async def _get(self, user_id: int, device_id: str) -> Optional[Device]:
        res = await self.db.execute(
            select(Device).where(Device.user_id == user_id, Device.id == device_id)
        )
        return res.scalars().first()

    # ── default display ──

    async def get_or_create_default(self, user_id: int) -> tuple[Device, bool]:
        res = await self.db.execute(
            select(Device).where(Device.user_id == user_id, Device.is_default.is_(True))
        )
        d = res.scalars().first()
        if d:
            return d, False
        d = Device(id=_gen_id(), user_id=user_id, name=DEFAULT_DEVICE_NAME, is_default=True)
        self.db.add(d)
        try:
            await self.db.commit()
        except IntegrityError:
            # Lost a race (concurrent first request) or a non-default tab owns
            # the reserved name — fetch what's there.
            await self.db.rollback()
            res = await self.db.execute(
                select(Device).where(Device.user_id == user_id, Device.is_default.is_(True))
            )
            existing = res.scalars().first()
            if existing:
                return existing, False
            d = Device(id=_gen_id(), user_id=user_id, name=f"{DEFAULT_DEVICE_NAME} ({_gen_id()[:4]})", is_default=True)
            self.db.add(d)
            await self.db.commit()
        await self.db.refresh(d)
        return d, True

    # ── the three beams ──

    async def beam_default(self, user_id: int, content: dict) -> tuple[dict, bool]:
        """Replace the default display's content. Returns (device, created)."""
        d, created = await self.get_or_create_default(user_id)
        await self._set_content(d, content)
        return serialize(d), created

    async def beam_new(
        self, user_id: int, name: Optional[str], content: Optional[dict],
        *, kind: str = "display", description: Optional[str] = None,
    ) -> dict:
        """Create a named entry (name generated if omitted). NameConflict if taken.
        kind 'lockbox' stashes it off the display; 'display' renders a tab."""
        if kind not in VALID_KINDS:
            raise ContentError(f'Invalid kind "{kind}". Must be one of: {", ".join(sorted(VALID_KINDS))}')
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ContentError("Device name must be a non-empty string")
        name = name.strip() if name else await self._free_name(user_id)
        d = Device(id=_gen_id(), user_id=user_id, name=name, kind=kind,
                   description=description.strip() if description else None)
        if content:
            d.content_type = content["type"]
            d.content_body = validate_content(content["type"], content.get("body"))
            d.content_updated_at = datetime.utcnow()
        self.db.add(d)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise NameConflict(f'A tab named "{name}" already exists')
        await self.db.refresh(d)
        return serialize(d)

    async def beam_existing(self, user_id: int, device_id: str, content: dict) -> Optional[tuple[dict, bool]]:
        """Replace content on a known tab. Beaming to an archived tab restores it
        (the id can only have come from the archive listing — showing content
        implies putting the surface back on the display). Returns
        (device, was_archived) or None if the id doesn't exist."""
        d = await self._get(user_id, device_id)
        if not d:
            return None
        was_archived = d.archived_at is not None
        d.archived_at = None
        await self._set_content(d, content)
        return serialize(d), was_archived

    async def _set_content(self, d: Device, content: Optional[dict]) -> None:
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

    async def _free_name(self, user_id: int) -> str:
        res = await self.db.execute(select(Device.name).where(Device.user_id == user_id))
        taken = {n.lower() for (n,) in res.all()}
        i = 2
        while f"tab {i}" in taken:
            i += 1
        return f"Tab {i}"

    # ── housekeeping ──

    async def clear(self, user_id: int, device_id: Optional[str]) -> Optional[dict]:
        """Blank a surface, keep the tab. device_id None → the default display."""
        if device_id is None:
            d, _ = await self.get_or_create_default(user_id)
        else:
            d = await self._get(user_id, device_id)
            if not d:
                return None
        await self._set_content(d, None)
        return serialize(d)

    async def rename(self, user_id: int, device_id: str, name: str) -> Optional[dict]:
        d = await self._get(user_id, device_id)
        if not d:
            return None
        if d.is_default:
            raise DefaultDeviceError("The default display can't be renamed")
        if not name or not name.strip():
            raise ContentError("Device name must be a non-empty string")
        d.name = name.strip()
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise NameConflict(f'A tab named "{name.strip()}" already exists')
        await self.db.refresh(d)
        return serialize(d)

    async def archive(self, user_id: int, device_id: str) -> Optional[dict]:
        d = await self._get(user_id, device_id)
        if not d:
            return None
        if d.is_default:
            raise DefaultDeviceError("The default display can't be archived")
        if d.archived_at is None:
            d.archived_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(d)
        return serialize(d)

    async def unarchive(self, user_id: int, device_id: str) -> Optional[dict]:
        d = await self._get(user_id, device_id)
        if not d:
            return None
        if d.archived_at is not None:
            d.archived_at = None
            await self.db.commit()
            await self.db.refresh(d)
        return serialize(d)

    async def delete(self, user_id: int, device_id: str) -> Optional[bool]:
        d = await self._get(user_id, device_id)
        if not d:
            return None
        if d.is_default:
            raise DefaultDeviceError("The default display can't be deleted — clear it instead")
        await self.db.delete(d)
        await self.db.commit()
        return True

    async def reset(self, user_id: int) -> Optional[dict]:
        """Delete every tab (including archived); the default survives, cleared.
        Returns the surviving default display."""
        await self.db.execute(
            delete(Device).where(Device.user_id == user_id, Device.is_default.is_(False))
        )
        await self.db.commit()
        d, _ = await self.get_or_create_default(user_id)
        await self._set_content(d, None)
        return serialize(d)
