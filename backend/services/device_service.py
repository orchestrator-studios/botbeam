"""Device (display tab) operations + content validation.

The agent-facing model: every user has one default display (always exists,
never renamed/archived/deleted) plus named tabs. The three beams map to
distinct service calls — beam_default (upsert the default's content),
beam_new (create, name must be free), beam_existing (replace content by id).
Names are unique per user; the agent resolves spoken names to ids via list().
"""
# Defer annotation evaluation to strings (PEP 563). This class defines a `list`
# method that would otherwise shadow the builtin when later methods' annotations
# (e.g. `-> list[dict]`) are evaluated eagerly at class-body time on Python <3.14,
# crashing import with "'function' object is not subscriptable".
from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime
from typing import Optional, get_args

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import Device, DeviceShare, User
from schemas import ContentType, DeviceKind

logger = logging.getLogger("botbeam.devices")

VALID_CONTENT_TYPES = set(get_args(ContentType))
VALID_KINDS = set(get_args(DeviceKind))
MAX_BODY_BYTES = 512 * 1024  # 500KB
DEFAULT_DEVICE_NAME = "Main"
_ALPHABET = string.ascii_letters + string.digits


class ContentError(ValueError):
    """Invalid content — surfaced as a 400."""


class NameConflict(ValueError):
    """Device name already in use for this user — surfaced as a 409."""


class DefaultDeviceError(ValueError):
    """Operation not allowed on the default display — surfaced as a 403."""


class ShareError(ValueError):
    """Invalid share request (bad email, unknown account, …) — surfaced as a 400."""


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


def serialize(
    d: Device, *, owner_email: Optional[str] = None, shared_with: Optional[list[str]] = None,
) -> dict:
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
        # ownerId always travels so any recipient (owner or grantee) can tell
        # whose device this is. owner_email/shared_with are set by the caller
        # only where they're meant to be seen (see schemas.Device).
        "ownerId": d.user_id,
        "ownerEmail": owner_email,
        "sharedWith": shared_with,
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
        rows = res.scalars().all()
        if summary:
            return [summarize(d) for d in rows]
        shares = await self._shares_map(user_id)
        return [serialize(d, shared_with=shares.get(d.id)) for d in rows]

    async def get(self, user_id: int, device_id: str) -> Optional[dict]:
        """Owner-or-grantee read. Own devices carry their grantee list; a device
        shared with you carries the owner's email (and never the grantee list)."""
        d = await self._get(user_id, device_id)
        if d:
            return serialize(d, shared_with=await self._shared_with_emails(d.id))
        d = await self._get_shared_to(user_id, device_id)
        if d:
            return serialize(d, owner_email=await self._owner_email(d.user_id))
        return None

    async def _get(self, user_id: int, device_id: str) -> Optional[Device]:
        """Owner-scoped fetch — the gate for every mutation (only the owner acts)."""
        res = await self.db.execute(
            select(Device).where(Device.user_id == user_id, Device.id == device_id)
        )
        return res.scalars().first()

    async def _get_shared_to(self, user_id: int, device_id: str) -> Optional[Device]:
        """A device shared *to* this user (any archived state — pins outlive archiving)."""
        res = await self.db.execute(
            select(Device)
            .join(DeviceShare, DeviceShare.device_id == Device.id)
            .where(DeviceShare.grantee_user_id == user_id, Device.id == device_id)
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
        logger.info("Default display created (user=%s, id=%s)", user_id, d.id)
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
        logger.info("Device created (user=%s, id=%s, kind=%s, name=%r)", user_id, d.id, kind, name)
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
        if content is None:
            logger.debug("Content cleared (device=%s)", d.id)
        else:
            logger.debug("Content set (device=%s, type=%s, bytes=%d)",
                         d.id, d.content_type, len(d.content_body.encode("utf-8")))

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
        logger.info("Device deleted (user=%s, id=%s)", user_id, device_id)
        return True

    async def reset(self, user_id: int) -> Optional[dict]:
        """Delete every tab (including archived); the default survives, cleared.
        Returns the surviving default display."""
        res = await self.db.execute(
            delete(Device).where(Device.user_id == user_id, Device.is_default.is_(False))
        )
        await self.db.commit()
        logger.info("Devices reset (user=%s, deleted=%d)", user_id, res.rowcount)
        d, _ = await self.get_or_create_default(user_id)
        await self._set_content(d, None)
        return serialize(d)

    # ── sharing (view-only grants to other accounts) ──

    async def shared_with_me(self, user_id: int) -> list[dict]:
        """Active (non-archived) devices other users have shared with this user,
        each tagged with the owner's email so the UI can show who shared it."""
        res = await self.db.execute(
            select(Device, User.email)
            .join(DeviceShare, DeviceShare.device_id == Device.id)
            .join(User, User.user_id == Device.user_id)
            .where(DeviceShare.grantee_user_id == user_id, Device.archived_at.is_(None))
            .order_by(Device.created_at)
        )
        return [serialize(d, owner_email=email) for d, email in res.all()]

    async def share(self, owner_id: int, device_id: str, grantee_email: str) -> Optional[dict]:
        """Grant a grantee (by email) view-only access to an owned display.
        Idempotent. Returns None if the device isn't the caller's; raises
        ShareError for a bad/unknown/self email. The returned dict carries the
        owner-facing device (with updated sharedWith), the grantee's user id, and
        the grantee-facing device payload (for the live 'device_shared' push)."""
        d = await self._get(owner_id, device_id)
        if not d:
            return None
        if d.kind != "display":
            raise ShareError("Only displays can be shared, not lockboxes")
        email = (grantee_email or "").strip()
        if not email:
            raise ShareError("An email is required")
        grantee = (await self.db.execute(
            select(User).where(User.email == email)  # utf8mb4_unicode_ci → case-insensitive
        )).scalars().first()
        if not grantee:
            raise ShareError(f"No BotBeam account for {email}")
        if grantee.user_id == owner_id:
            raise ShareError("You already own this display")
        exists = (await self.db.execute(select(DeviceShare).where(
            DeviceShare.device_id == device_id,
            DeviceShare.grantee_user_id == grantee.user_id,
        ))).scalars().first()
        if not exists:
            self.db.add(DeviceShare(device_id=device_id, grantee_user_id=grantee.user_id))
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()  # lost a race; the grant already exists
            logger.info("Device shared (owner=%s, device=%s, grantee=%s)", owner_id, device_id, grantee.user_id)
        owner_email = await self._owner_email(owner_id)
        return {
            "device": serialize(d, shared_with=await self._shared_with_emails(device_id)),
            "grantee_id": grantee.user_id,
            "grantee_device": serialize(d, owner_email=owner_email),
        }

    async def unshare(self, owner_id: int, device_id: str, grantee_email: str) -> Optional[dict]:
        """Revoke a grantee's access. Returns the owner-facing device (updated
        sharedWith) and the revoked grantee's id (None if no such account), or
        None if the device isn't the caller's."""
        d = await self._get(owner_id, device_id)
        if not d:
            return None
        grantee = (await self.db.execute(
            select(User).where(User.email == (grantee_email or "").strip())
        )).scalars().first()
        grantee_id = grantee.user_id if grantee else None
        if grantee_id is not None:
            await self.db.execute(delete(DeviceShare).where(
                DeviceShare.device_id == device_id,
                DeviceShare.grantee_user_id == grantee_id,
            ))
            await self.db.commit()
            logger.info("Device unshared (owner=%s, device=%s, grantee=%s)", owner_id, device_id, grantee_id)
        return {
            "device": serialize(d, shared_with=await self._shared_with_emails(device_id)),
            "grantee_id": grantee_id,
        }

    async def list_shares(self, owner_id: int, device_id: str) -> Optional[list[str]]:
        """Emails an owned device is shared with (None if not the caller's)."""
        d = await self._get(owner_id, device_id)
        if not d:
            return None
        return await self._shared_with_emails(device_id)

    async def grantee_ids(self, device_id: str) -> list[int]:
        """User ids a device is shared with — used to fan WS events out to viewers."""
        res = await self.db.execute(
            select(DeviceShare.grantee_user_id).where(DeviceShare.device_id == device_id)
        )
        return [g for (g,) in res.all()]

    async def grantee_map(self, owner_id: int) -> dict[str, list[int]]:
        """{device_id: [grantee_user_id, …]} across all of the owner's devices —
        captured before a reset so each viewer can be told their share vanished."""
        res = await self.db.execute(
            select(DeviceShare.device_id, DeviceShare.grantee_user_id)
            .join(Device, Device.id == DeviceShare.device_id)
            .where(Device.user_id == owner_id)
        )
        out: dict[str, list[int]] = {}
        for did, gid in res.all():
            out.setdefault(did, []).append(gid)
        return out

    async def _shared_with_emails(self, device_id: str) -> list[str]:
        res = await self.db.execute(
            select(User.email)
            .join(DeviceShare, DeviceShare.grantee_user_id == User.user_id)
            .where(DeviceShare.device_id == device_id)
            .order_by(User.email)
        )
        return [e for (e,) in res.all()]

    async def _shares_map(self, owner_id: int) -> dict[str, list[str]]:
        """{device_id: [grantee_email, …]} for one owner's devices in a single query."""
        res = await self.db.execute(
            select(DeviceShare.device_id, User.email)
            .join(Device, Device.id == DeviceShare.device_id)
            .join(User, User.user_id == DeviceShare.grantee_user_id)
            .where(Device.user_id == owner_id)
            .order_by(User.email)
        )
        out: dict[str, list[str]] = {}
        for did, email in res.all():
            out.setdefault(did, []).append(email)
        return out

    async def _owner_email(self, user_id: int) -> Optional[str]:
        res = await self.db.execute(select(User.email).where(User.user_id == user_id))
        return res.scalar_one_or_none()
