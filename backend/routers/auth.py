from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import get_async_db
from schemas import RegisterRequest, LoginRequest, Token, Me, AgentTokenRequest, AgentToken
from services import auth_service
from services.user_service import UserService

router = APIRouter()


@router.post("/register", response_model=Token, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_async_db)):
    us = UserService(db)
    if await us.get_user_by_email(body.email.lower()):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await us.create_user(body.email.lower(), body.password, body.full_name)
    return auth_service.token_response(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    user = await UserService(db).verify_credentials(body.email.lower(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return auth_service.token_response(user, settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.get("/me", response_model=Me)
async def me(user=Depends(auth_service.get_current_user)):
    return Me(
        user_id=user.user_id, org_id=user.org_id, role=user.role.value,
        email=user.email, username=user.email.split("@")[0],
    )


@router.post("/agent-token", response_model=AgentToken, status_code=201)
async def agent_token(body: Optional[AgentTokenRequest] = None, user=Depends(auth_service.get_current_user)):
    name = body.name if (body and body.name) else "orchestra"
    token = auth_service.create_access_token(user, settings.AGENT_TOKEN_EXPIRE_MINUTES)
    return AgentToken(access_token=token, name=name)
