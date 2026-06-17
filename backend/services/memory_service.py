"""Memory operations + validation — the agent's durable, typed fact store.

A memory is a small, titled fact the agent writes and recalls later — distinct
from a Device: it isn't rendered (no tab) and isn't a one-off payload (lockbox).
It's addressed by a stable per-user `key` with upsert semantics on write, and
recalled three ways: list (summaries), get one by key (full), or text-search
across key/description/body. Scoped to its owner.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, get_args

from sqlalchemy import select, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import Memory
from schemas import MemoryCategory

logger = logging.getLogger("botbeam.memories")

VALID_CATEGORIES = set(get_args(MemoryCategory))
DEFAULT_CATEGORY = "note"
MAX_BODY_BYTES = 64 * 1024          # 64KB — facts, not payloads (stash large blobs in a lockbox)
MAX_KEY_LEN = 255
MAX_DESCRIPTION_LEN = 500


class MemoryError(ValueError):
    """Invalid memory input — surfaced as a 400."""


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return (dt.isoformat() + "Z") if dt else None


def validate_key(key: str) -> str:
    if not key or not key.strip():
        raise MemoryError("Memory key is required")
    key = key.strip()
    if len(key) > MAX_KEY_LEN:
        raise MemoryError(f"Memory key too long (max {MAX_KEY_LEN} chars)")
    if "/" in key:
        raise MemoryError("Memory key can't contain '/'")
    return key


def validate_fields(
    category: Optional[str], description: Optional[str], body,
) -> tuple[str, Optional[str], str]:
    cat = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    if cat not in VALID_CATEGORIES:
        raise MemoryError(f'Invalid category "{cat}". Must be one of: {", ".join(sorted(VALID_CATEGORIES))}')
    if not isinstance(body, str):
        raise MemoryError("Memory body must be a string")
    if not body.strip():
        raise MemoryError("Memory body is required")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise MemoryError(
            f"Memory body too large (max {MAX_BODY_BYTES // 1024}KB) — stash large payloads in a lockbox instead")
    desc = description.strip() if description and description.strip() else None
    if desc and len(desc) > MAX_DESCRIPTION_LEN:
        raise MemoryError(f"Description too long (max {MAX_DESCRIPTION_LEN} chars)")
    return cat, desc, body


def serialize(m: Memory) -> dict:
    return {
        "key": m.key,
        "category": m.category,
        "description": m.description,
        "body": m.body,
        "createdAt": _iso(m.created_at),
        "updatedAt": _iso(m.updated_at),
    }


def summarize(m: Memory) -> dict:
    """Cheap recall listing — no body."""
    return {
        "key": m.key,
        "category": m.category,
        "description": m.description,
        "updatedAt": _iso(m.updated_at),
    }


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self, user_id: int, q: Optional[str] = None, category: Optional[str] = None,
    ) -> list[dict]:
        """Recall: summaries (no body), newest first. `q` text-searches
        key/description/body; `category` filters to one bucket. Both optional."""
        conds = [Memory.user_id == user_id]
        if category:
            if category not in VALID_CATEGORIES:
                raise MemoryError(
                    f'Invalid category "{category}". Must be one of: {", ".join(sorted(VALID_CATEGORIES))}')
            conds.append(Memory.category == category)
        if q and q.strip():
            term = q.strip()
            conds.append(or_(
                Memory.key.contains(term, autoescape=True),
                Memory.description.contains(term, autoescape=True),
                Memory.body.contains(term, autoescape=True),
            ))
        res = await self.db.execute(
            select(Memory).where(*conds).order_by(Memory.updated_at.desc())
        )
        return [summarize(m) for m in res.scalars().all()]

    async def get(self, user_id: int, key: str) -> Optional[dict]:
        m = await self._get(user_id, key)
        return serialize(m) if m else None

    async def _get(self, user_id: int, key: str) -> Optional[Memory]:
        """Owner-scoped fetch. Key match is case-insensitive (utf8mb4_unicode_ci)."""
        res = await self.db.execute(
            select(Memory).where(Memory.user_id == user_id, Memory.key == key)
        )
        return res.scalars().first()

    async def upsert(
        self, user_id: int, key: str, category: Optional[str], description: Optional[str], body,
    ) -> dict:
        """Set the memory at `key` (create or replace). Idempotent."""
        key = validate_key(key)
        cat, desc, body = validate_fields(category, description, body)
        m = await self._get(user_id, key)
        created = m is None
        if m is None:
            m = Memory(user_id=user_id, key=key)
            self.db.add(m)
        m.category, m.description, m.body = cat, desc, body
        try:
            await self.db.commit()
        except IntegrityError:
            # Lost a create race — the winner's row exists now; replace its content.
            await self.db.rollback()
            m = await self._get(user_id, key)
            if m is None:
                raise
            m.category, m.description, m.body = cat, desc, body
            await self.db.commit()
            created = False
        await self.db.refresh(m)
        logger.info("Memory %s (user=%s, key=%r, category=%s)",
                    "created" if created else "updated", user_id, key, cat)
        return serialize(m)

    async def delete(self, user_id: int, key: str) -> Optional[bool]:
        m = await self._get(user_id, key)
        if not m:
            return None
        await self.db.delete(m)
        await self.db.commit()
        logger.info("Memory deleted (user=%s, key=%r)", user_id, key)
        return True

    async def reset(self, user_id: int) -> int:
        res = await self.db.execute(delete(Memory).where(Memory.user_id == user_id))
        await self.db.commit()
        logger.info("Memories reset (user=%s, deleted=%d)", user_id, res.rowcount)
        return res.rowcount
