from typing import AsyncGenerator
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import pymysql
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from config.settings import settings
from models import Base

pymysql.install_as_MySQLdb()


def _ensure_charset(url: str, charset: str = "utf8mb4") -> str:
    """Force the client connection to utf8mb4 so 4-byte chars (emoji, CJK, …)
    round-trip correctly regardless of the server/db default charset."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.setdefault("charset", charset)
    return urlunsplit(parts._replace(query=urlencode(query)))


def _to_async_url(url: str) -> str:
    if url.startswith("mysql+pymysql://"):
        url = "mysql+aiomysql://" + url[len("mysql+pymysql://"):]
    elif url.startswith("mysql://"):
        url = "mysql+aiomysql://" + url[len("mysql://"):]
    if url.startswith("mysql+aiomysql://"):
        url = _ensure_charset(url)
    return url


# NullPool: a fresh connection per checkout instead of a held pool. Idle pooled
# aiomysql connections die (transport closed) and then 500 every request that
# draws them — under uvloop the failure is a RuntimeError, which escapes
# pool_pre_ping's recycle logic entirely. Connecting to same-region RDS costs a
# few ms; this app's traffic doesn't justify a pool.
async_engine = create_async_engine(
    _to_async_url(settings.DATABASE_URL),
    poolclass=NullPool,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        await session.close()


async def init_async_db() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_devices(conn)


async def _migrate_devices(conn) -> None:
    """Bring a pre-existing devices table up to the current schema (no Alembic yet).
    create_all only creates missing tables — it never alters columns/indexes."""
    from sqlalchemy import text

    cols = {
        row[0] for row in (await conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'devices'"
        ))).fetchall()
    }
    if not cols:  # fresh DB — create_all already built the full table
        return
    if "is_default" not in cols:
        await conn.execute(text(
            "ALTER TABLE devices ADD COLUMN is_default TINYINT(1) NOT NULL DEFAULT 0"
        ))
    if "archived_at" not in cols:
        await conn.execute(text("ALTER TABLE devices ADD COLUMN archived_at DATETIME NULL"))
    if "description" not in cols:
        await conn.execute(text("ALTER TABLE devices ADD COLUMN description TEXT NULL"))
    if "kind" not in cols:
        await conn.execute(text(
            "ALTER TABLE devices ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'display'"
        ))

    indexes = {
        row[0] for row in (await conn.execute(text(
            "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'devices'"
        ))).fetchall()
    }
    if "uq_device_user_name" not in indexes:
        # Names are about to become unique per user — de-dupe survivors first
        # (keep the oldest, suffix the rest), then add the constraint.
        dupes = (await conn.execute(text(
            "SELECT DISTINCT d.id FROM devices d JOIN devices earlier "
            "ON earlier.user_id = d.user_id AND earlier.name = d.name "
            "AND (earlier.created_at < d.created_at "
            "     OR (earlier.created_at = d.created_at AND earlier.id < d.id))"
        ))).fetchall()
        for (dev_id,) in dupes:
            await conn.execute(text(
                "UPDATE devices SET name = CONCAT(name, ' (', :suffix, ')') WHERE id = :id"
            ), {"suffix": dev_id[:4], "id": dev_id})
        await conn.execute(text(
            "ALTER TABLE devices ADD CONSTRAINT uq_device_user_name UNIQUE (user_id, name)"
        ))
