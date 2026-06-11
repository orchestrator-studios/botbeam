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
