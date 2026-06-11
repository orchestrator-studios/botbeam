from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    org_id: Optional[int] = None
    role: str
    email: str
    username: str


class Me(BaseModel):
    user_id: int
    org_id: Optional[int] = None
    role: str
    email: str
    username: str


class AgentTokenRequest(BaseModel):
    name: Optional[str] = "orchestra"


class AgentToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str
