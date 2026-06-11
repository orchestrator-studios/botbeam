import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import get_async_db
from schemas import User
from services import auth_service
from services.user_service import UserService

logger = logging.getLogger("botbeam.auth")


# ── request/response wrappers (specific to these endpoints, not domain objects) ──
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AgentTokenRequest(BaseModel):
    name: Optional[str] = "orchestra"


class AuthResponse(User):
    """The signed-in user plus their bearer token (register/login)."""
    access_token: str
    token_type: str = "bearer"


class AgentTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str


router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_async_db)):
    us = UserService(db)
    if await us.get_user_by_email(body.email.lower()):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await us.create_user(body.email.lower(), body.password, body.full_name)
    logger.info("User registered (user=%s, email=%s)", user.user_id, user.email)
    return auth_service.token_response(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    user = await UserService(db).verify_credentials(body.email.lower(), body.password)
    if not user:
        logger.warning("Login failed (email=%s)", body.email.lower())
        raise HTTPException(status_code=401, detail="Invalid email or password")
    logger.info("Login (user=%s)", user.user_id)
    return auth_service.token_response(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.get("/me", response_model=User)
async def me(user=Depends(auth_service.get_current_user)):
    return User(
        user_id=user.user_id, org_id=user.org_id, role=user.role.value,
        email=user.email, username=user.email.split("@")[0],
    )


@router.post("/agent-token", response_model=AgentTokenResponse, status_code=201)
async def agent_token(body: Optional[AgentTokenRequest] = None, user=Depends(auth_service.get_current_user)):
    name = body.name if (body and body.name) else "orchestra"
    token = auth_service.create_access_token(user, settings.AGENT_TOKEN_EXPIRE_MINUTES)
    logger.info("Agent token issued (user=%s, name=%s, ttl_days=%d)",
                user.user_id, name, settings.AGENT_TOKEN_EXPIRE_MINUTES // (60 * 24))
    return AgentTokenResponse(access_token=token, name=name)
