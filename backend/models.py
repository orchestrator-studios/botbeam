from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UserRole(str, PyEnum):
    """Matches the kh / table-that role enum."""
    PLATFORM_ADMIN = "platform_admin"   # org_id = NULL; above all orgs
    ORG_ADMIN = "org_admin"             # manages their org's members
    MEMBER = "member"                   # regular user in an org


class Organization(Base):
    __tablename__ = "organizations"

    org_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

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
    """A display tab. Scoped directly to its owning user (no separate namespace)."""
    __tablename__ = "devices"

    id = Column(String(16), primary_key=True)              # public handle (the API/skill uses this)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    content_type = Column(String(20), nullable=True)
    content_body = Column(LONGTEXT, nullable=True)
    content_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
