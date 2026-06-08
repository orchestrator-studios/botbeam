"""JWT (HS256) + bcrypt auth — the kh / table-that house pattern."""
import time
from datetime import datetime, timedelta

from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import get_async_db
from models import User
from services.user_service import UserService

_security = HTTPBearer(auto_error=False)


def create_access_token(user: User, minutes: int) -> str:
    payload = {
        "sub": user.email,
        "user_id": user.user_id,
        "org_id": user.org_id,
        "username": user.email.split("@")[0],
        "role": user.role.value,
        "iat": int(time.time()),
        "exp": datetime.utcnow() + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)


def token_response(user: User, minutes: int) -> dict:
    return {
        "access_token": create_access_token(user, minutes),
        "token_type": "bearer",
        "user_id": user.user_id,
        "org_id": user.org_id,
        "role": user.role.value,
        "email": user.email,
        "username": user.email.split("@")[0],
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_security),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await UserService(db).get_user_by_id(payload.get("user_id"))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user
