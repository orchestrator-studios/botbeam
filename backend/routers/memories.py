"""Memory routes — the agent's durable, typed fact store.

Addressed by a stable per-user `key` (upsert on write):
  GET    /memories            recall — list / text-search (summaries, no body)
  GET    /memories/{key}      read one in full; 404 if missing
  PUT    /memories/{key}      remember — upsert (create or replace)
  DELETE /memories/{key}      forget one; 404 if missing
  DELETE /memories            forget all
Memories aren't rendered, so (unlike devices) there are no WebSocket broadcasts.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from schemas import Memory, MemorySummary, MemoryCategory
from services.auth_service import get_current_user
from services.memory_service import MemoryService, MemoryError


class MemoryWrite(BaseModel):
    """remember: category/description optional (category defaults to 'note'); body required."""
    category: Optional[MemoryCategory] = None
    description: Optional[str] = None
    body: str = Field(min_length=1)


router = APIRouter()


def _svc(db: AsyncSession) -> MemoryService:
    return MemoryService(db)


@router.get("/memories", response_model=list[MemorySummary])
async def list_memories(
    q: str | None = None, category: str | None = None,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        return await _svc(db).list(user.user_id, q=q, category=category)
    except MemoryError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/memories/{key}", response_model=Memory)
async def get_memory(key: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    m = await _svc(db).get(user.user_id, key)
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    return m


@router.put("/memories/{key}", response_model=Memory)
async def put_memory(
    key: str, body: MemoryWrite,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        return await _svc(db).upsert(user.user_id, key, body.category, body.description, body.body)
    except MemoryError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/memories/{key}", status_code=204)
async def delete_memory(key: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    ok = await _svc(db).delete(user.user_id, key)
    if ok is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(status_code=204)


@router.delete("/memories", status_code=204)
async def reset_memories(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await _svc(db).reset(user.user_id)
    return Response(status_code=204)
