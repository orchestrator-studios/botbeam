from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Every table stores utf8mb4 so rich text (emoji, CJK, symbols, any language)
# round-trips losslessly. Binary assets live in object storage (S3), referenced
# here by URL — the DB stays text/metadata only.
_UTF8MB4 = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class UserRole(str, PyEnum):
    """Matches the kh / table-that role enum."""
    PLATFORM_ADMIN = "platform_admin"   # org_id = NULL; above all orgs
    ORG_ADMIN = "org_admin"             # manages their org's members
    MEMBER = "member"                   # regular user in an org


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = _UTF8MB4

    org_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    __table_args__ = _UTF8MB4

    user_id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.org_id"), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)          # bcrypt hash
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x], name="userrole"),
        default=UserRole.MEMBER, nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    """A user-owned entry in the key-value store. Scoped directly to its owner.

    `kind` decides how it surfaces: 'display' entries are rendered live as tabs on
    the user's screen; 'lockbox' entries are stashed — written by the user or their
    agent in one context and retrieved in another — and listed separately rather
    than rendered. Both share one lifecycle: beam content, read it, archive when done.

    Names are unique per user (case-insensitive via utf8mb4_unicode_ci) — the
    agent resolves user-spoken names against them, so they must be unambiguous.
    Each user has exactly one default display (is_default) that always exists
    and can't be renamed, archived, or deleted.

    `description` is optional human-readable context — especially important for
    lockboxes, which aren't rendered, so the listing needs a summary of the payload.
    """
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_device_user_name"),
        _UTF8MB4,
    )

    id = Column(String(16), primary_key=True)              # public handle (the API/skill uses this)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)               # optional summary; key for lockboxes (not rendered)
    is_default = Column(Boolean, default=False, nullable=False)
    kind = Column(String(16), default="display", nullable=False)  # 'display' (rendered tab) | 'lockbox' (stashed)
    archived_at = Column(DateTime, nullable=True)          # non-null = off the display, restorable
    content_type = Column(String(20), nullable=True)
    content_body = Column(LONGTEXT, nullable=True)
    content_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeviceShare(Base):
    """A view-only grant of a device to another user.

    The device's owner creates these (by the grantee's email); the grantee then
    sees the device under "Shared with me" and watches its live content, but
    can't modify it — only the owner can beam/rename/archive/delete. Deleting the
    row revokes access. Rows cascade away when either the device or the grantee
    is removed. One row per (device, grantee); re-sharing is idempotent.
    """
    __tablename__ = "device_shares"
    __table_args__ = (
        UniqueConstraint("device_id", "grantee_user_id", name="uq_share_device_grantee"),
        _UTF8MB4,
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(16), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False)
    grantee_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
