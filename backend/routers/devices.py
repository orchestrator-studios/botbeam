"""Device routes — the agent/browser contract.

Three beams, three endpoints, distinct failure modes:
  PUT  /devices/default/content  beam-default (default display always exists)
  POST /devices                  beam-new     (409 if the name is taken)
  PUT  /devices/{id}/content     beam-existing (404 if the id doesn't)
`default` is a reserved path segment — device ids are 8 alphanumerics, no collision.
Every mutation broadcasts to the owner's WebSocket channel.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from schemas import Content, DeviceCreate, RenameRequest
from services.auth_service import get_current_user
from services.device_service import (
    DeviceService, ContentError, NameConflict, DefaultDeviceError,
)
from websocket import manager

router = APIRouter()


def _svc(db: AsyncSession) -> DeviceService:
    return DeviceService(db)


@router.get("/devices")
async def list_devices(
    archived: bool = False, view: str = "full",
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    if view not in ("full", "summary"):
        raise HTTPException(status_code=400, detail='view must be "full" or "summary"')
    return await _svc(db).list(user.user_id, archived=archived, summary=(view == "summary"))


@router.get("/devices/{device_id}")
async def get_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).get(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev


# ── the three beams ──

@router.put("/devices/default/content")
async def beam_default(body: Content, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        dev, created = await _svc(db).beam_default(user.user_id, body.model_dump())
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    event = "device_created" if created else "device_updated"
    await manager.broadcast(user.user_id, {"event": event, "device": dev})
    return dev


@router.post("/devices", status_code=201)
async def beam_new(body: DeviceCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    content = body.content.model_dump() if body.content else None
    try:
        dev = await _svc(db).beam_new(user.user_id, body.name, content)
    except NameConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await manager.broadcast(user.user_id, {"event": "device_created", "device": dev})
    return dev


@router.put("/devices/{device_id}/content")
async def beam_existing(
    device_id: str, body: Content,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await _svc(db).beam_existing(user.user_id, device_id, body.model_dump())
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Device not found")
    dev, was_archived = result
    if was_archived:
        await manager.broadcast(user.user_id, {"event": "device_unarchived", "device": dev})
    await manager.broadcast(user.user_id, {"event": "device_updated", "device": dev})
    return dev


# ── housekeeping ──

@router.delete("/devices/default/content")
async def clear_default(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).clear(user.user_id, None)
    await manager.broadcast(user.user_id, {"event": "device_updated", "device": dev})
    return dev


@router.delete("/devices/{device_id}/content")
async def clear_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).clear(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_updated", "device": dev})
    return dev


@router.patch("/devices/{device_id}")
async def rename_device(
    device_id: str, body: RenameRequest,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        dev = await _svc(db).rename(user.user_id, device_id, body.name)
    except DefaultDeviceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except NameConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_updated", "device": dev})
    return dev


@router.post("/devices/{device_id}/archive")
async def archive_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        dev = await _svc(db).archive(user.user_id, device_id)
    except DefaultDeviceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_archived", "deviceId": device_id})
    return dev


@router.post("/devices/{device_id}/unarchive")
async def unarchive_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).unarchive(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_unarchived", "device": dev})
    return dev


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        ok = await _svc(db).delete(user.user_id, device_id)
    except DefaultDeviceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if ok is None:
        raise HTTPException(status_code=404, detail="Device not found")
    await manager.broadcast(user.user_id, {"event": "device_deleted", "deviceId": device_id})
    return Response(status_code=204)


@router.delete("/devices", status_code=204)
async def reset_devices(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    await _svc(db).reset(user.user_id)
    await manager.broadcast(user.user_id, {"event": "devices_reset"})
    return Response(status_code=204)
