"""User + organization operations. Mirrors the kh / table-that UserService."""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from models import User, Organization, UserRole

logger = logging.getLogger("botbeam.users")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEFAULT_ORG_NAME = "Default Organization"


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        res = await self.db.execute(select(User).where(User.user_id == user_id))
        return res.scalars().first()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        res = await self.db.execute(select(User).where(User.email == email))
        return res.scalars().first()

    async def get_or_create_default_org(self) -> Organization:
        res = await self.db.execute(select(Organization).where(Organization.name == DEFAULT_ORG_NAME))
        org = res.scalars().first()
        if org:
            return org
        org = Organization(name=DEFAULT_ORG_NAME)
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)
        logger.info("Default org created (org_id=%s)", org.org_id)
        return org

    async def create_user(
        self, email: str, password: str, full_name: Optional[str] = None, role: UserRole = UserRole.MEMBER
    ) -> User:
        org = await self.get_or_create_default_org()
        user = User(
            email=email,
            password=pwd_context.hash(password),
            full_name=full_name,
            role=role,
            org_id=org.org_id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def verify_credentials(self, email: str, password: str) -> Optional[User]:
        user = await self.get_user_by_email(email)
        if not user or not pwd_context.verify(password, user.password):
            return None
        if not user.is_active:
            return None
        return user
