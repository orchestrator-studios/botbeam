from fastapi import APIRouter, Depends, HTTPException, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from schemas import DeviceCreate
from services.auth_service import get_current_user
from services.device_service import DeviceService, ContentError
from websocket import manager

router = APIRouter()


@router.get("/devices")
async def list_devices(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await DeviceService(db).list(user.user_id)


@router.post("/devices", status_code=201)
async def create_device(body: DeviceCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    content = body.content.model_dump() if body.content else None
    try:
        dev = await DeviceService(db).create(user.user_id, body.name, content)
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await manager.broadcast(user.user_id, {"event": "device_created", "device": dev})
    return dev


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: str, payload: dict = Body(...),
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    name = payload.get("name")
    content_provided = "content" in payload
    if name is None and not content_provided:
        raise HTTPException(status_code=400, detail="name or content is required")
    try:
        dev = await DeviceService(db).update(
            user.user_id, device_id,
            name=name, content_provided=content_provided, content=payload.get("content"),
        )
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_updated", "device": dev})
    return dev


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    if not await DeviceService(db).delete(user.user_id, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_deleted", "deviceId": device_id})
    return Response(status_code=204)


@router.delete("/devices", status_code=204)
async def reset_devices(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await DeviceService(db).reset(user.user_id)
    await manager.broadcast(user.user_id, {"event": "devices_reset"})
    return Response(status_code=204)
