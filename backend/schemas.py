"""Domain objects — the API representations shared across endpoints.

Endpoint-specific request/response wrappers live beside their endpoints
(routers/auth.py, routers/devices.py). This file mirrors
frontend/src/types/index.ts — same objects, same order; keep them in sync.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ── User ──
class User(BaseModel):
    user_id: int
    org_id: Optional[int] = None
    role: str
    email: str
    username: str


# ── Devices ──
DeviceKind = Literal["display", "lockbox"]

ContentType = Literal[
    "text", "markdown", "html", "url", "image", "list", "dashboard", "table", "json",
]


class DeviceContent(BaseModel):
    type: ContentType
    body: str
    updatedAt: Optional[str] = None


class Device(BaseModel):
    """Full device, as returned by the device endpoints (matches serialize())."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: Optional[str] = None
    kind: DeviceKind
    isDefault: bool
    archivedAt: Optional[str] = None
    createdAt: Optional[str] = None
    content: Optional[DeviceContent] = None
    # ── sharing ──
    # ownerId is always set: a viewer compares it to their own id to tell an
    # owned device from one shared with them. ownerEmail is populated only when
    # the device is shown to a grantee (who shared it). sharedWith is the owner's
    # grantee list — populated only in the owner's own views, never to grantees.
    ownerId: Optional[int] = None
    ownerEmail: Optional[str] = None
    sharedWith: Optional[list[str]] = None


class DeviceSummary(BaseModel):
    """Lightweight listing — no content bodies (view=summary; matches summarize())."""
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: Optional[str] = None
    kind: DeviceKind
    isDefault: bool
    archivedAt: Optional[str] = None
    contentType: Optional[ContentType] = None
    contentUpdatedAt: Optional[str] = None
    createdAt: Optional[str] = None


# ── Memories ──
MemoryCategory = Literal["user", "project", "reference", "feedback", "note"]


class Memory(BaseModel):
    """A durable, typed fact (matches memory_service.serialize())."""
    model_config = ConfigDict(extra="forbid")
    key: str
    category: MemoryCategory
    description: Optional[str] = None
    body: str
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class MemorySummary(BaseModel):
    """Recall listing — no body (matches memory_service.summarize())."""
    model_config = ConfigDict(extra="forbid")
    key: str
    category: MemoryCategory
    description: Optional[str] = None
    updatedAt: Optional[str] = None
