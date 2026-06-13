"""Device routes — the agent/browser contract.

Three beams, three endpoints, distinct failure modes:
  PUT  /devices/default/content  beam-default (default display always exists)
  POST /devices                  beam-new     (409 if the name is taken)
  PUT  /devices/{id}/content     beam-existing (404 if the id doesn't)
`default` is a reserved path segment — device ids are 8 alphanumerics, no collision.
Every mutation broadcasts to the owner's WebSocket channel.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_async_db
from schemas import Device, DeviceKind, DeviceSummary
from services.auth_service import get_current_user
from services.device_service import (
    DeviceService, ContentError, NameConflict, DefaultDeviceError, ShareError,
)
from websocket import manager


# ── request payloads (specific to these endpoints, not domain objects) ──
class Content(BaseModel):
    type: str
    body: str


class ShareRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)


class DeviceCreate(BaseModel):
    """beam-new: name optional (server generates one), content optional (empty tab).
    kind 'lockbox' stashes the entry off-screen; 'display' (default) renders a tab."""
    name: Optional[str] = None
    description: Optional[str] = None
    kind: DeviceKind = "display"
    content: Optional[Content] = None


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


router = APIRouter()


def _svc(db: AsyncSession) -> DeviceService:
    return DeviceService(db)


async def _emit(db: AsyncSession, owner_id: int, device_id: str, message: dict) -> None:
    """Broadcast a device event to the owner and everyone it's shared with, so a
    grantee's screen (or pinned kiosk) tracks the owner's beams live."""
    await manager.broadcast(owner_id, message)
    for gid in await _svc(db).grantee_ids(device_id):
        await manager.broadcast(gid, message)


@router.get("/devices", response_model=list[Device] | list[DeviceSummary])
async def list_devices(
    archived: bool = False, view: str = "full", kind: str | None = None,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    if view not in ("full", "summary"):
        raise HTTPException(status_code=400, detail='view must be "full" or "summary"')
    if kind is not None and kind not in ("display", "lockbox"):
        raise HTTPException(status_code=400, detail='kind must be "display" or "lockbox"')
    return await _svc(db).list(
        user.user_id, archived=archived, summary=(view == "summary"), kind=kind,
    )


# Registered before /devices/{device_id} so "shared" isn't taken for an id.
@router.get("/devices/shared", response_model=list[Device])
async def list_shared_with_me(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    return await _svc(db).shared_with_me(user.user_id)


@router.get("/devices/{device_id}", response_model=Device)
async def get_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    # Owner-or-grantee read (a shared device is visible to its grantees).
    dev = await _svc(db).get(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev


# ── the three beams ──

@router.put("/devices/default/content", response_model=Device)
async def beam_default(body: Content, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        dev, created = await _svc(db).beam_default(user.user_id, body.model_dump())
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    event = "device_created" if created else "device_updated"
    await _emit(db, user.user_id, dev["id"], {"event": event, "device": dev})
    return dev


@router.post("/devices", status_code=201, response_model=Device)
async def beam_new(body: DeviceCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    content = body.content.model_dump() if body.content else None
    try:
        dev = await _svc(db).beam_new(
            user.user_id, body.name, content, kind=body.kind, description=body.description,
        )
    except NameConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ContentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await manager.broadcast(user.user_id, {"event": "device_created", "device": dev})
    return dev


@router.put("/devices/{device_id}/content", response_model=Device)
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
        await _emit(db, user.user_id, dev["id"], {"event": "device_unarchived", "device": dev})
    await _emit(db, user.user_id, dev["id"], {"event": "device_updated", "device": dev})
    return dev


# ── housekeeping ──

@router.delete("/devices/default/content", response_model=Device)
async def clear_default(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).clear(user.user_id, None)
    await _emit(db, user.user_id, dev["id"], {"event": "device_updated", "device": dev})
    return dev


@router.delete("/devices/{device_id}/content", response_model=Device)
async def clear_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).clear(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await _emit(db, user.user_id, device_id, {"event": "device_updated", "device": dev})
    return dev


@router.patch("/devices/{device_id}", response_model=Device)
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
    await _emit(db, user.user_id, device_id, {"event": "device_updated", "device": dev})
    return dev


@router.post("/devices/{device_id}/archive", response_model=Device)
async def archive_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    try:
        dev = await _svc(db).archive(user.user_id, device_id)
    except DefaultDeviceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    # Grantees drop an archived device from their "Shared with me" list.
    await _emit(db, user.user_id, device_id, {"event": "device_archived", "deviceId": device_id})
    return dev


@router.post("/devices/{device_id}/unarchive", response_model=Device)
async def unarchive_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    dev = await _svc(db).unarchive(user.user_id, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    await _emit(db, user.user_id, device_id, {"event": "device_unarchived", "device": dev})
    return dev


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    # Capture grantees before the row (and its share rows) cascade away.
    grantees = await _svc(db).grantee_ids(device_id)
    try:
        ok = await _svc(db).delete(user.user_id, device_id)
    except DefaultDeviceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if ok is None:
        raise HTTPException(status_code=404, detail="Device not found")
    msg = {"event": "device_deleted", "deviceId": device_id}
    await manager.broadcast(user.user_id, msg)
    for gid in grantees:
        await manager.broadcast(gid, msg)
    return Response(status_code=204)


@router.delete("/devices", status_code=204)
async def reset_devices(user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    # Capture who was viewing each shared device before they're deleted, so each
    # grantee can be told their share vanished (a blanket reset isn't theirs).
    grantee_map = await _svc(db).grantee_map(user.user_id)
    await _svc(db).reset(user.user_id)
    await manager.broadcast(user.user_id, {"event": "devices_reset"})
    for did, gids in grantee_map.items():
        for gid in gids:
            await manager.broadcast(gid, {"event": "device_deleted", "deviceId": did})
    return Response(status_code=204)


# ── sharing (view-only grants to other accounts) ──

@router.get("/devices/{device_id}/shares", response_model=list[str])
async def list_device_shares(device_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    emails = await _svc(db).list_shares(user.user_id, device_id)
    if emails is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return emails


@router.post("/devices/{device_id}/shares", response_model=Device)
async def share_device(
    device_id: str, body: ShareRequest,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    try:
        result = await _svc(db).share(user.user_id, device_id, body.email)
    except ShareError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Device not found")
    # Tell the grantee's open sessions a new shared device is available.
    await manager.broadcast(result["grantee_id"], {"event": "device_shared", "device": result["grantee_device"]})
    return result["device"]


@router.delete("/devices/{device_id}/shares", response_model=Device)
async def unshare_device(
    device_id: str, email: str,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_async_db),
):
    result = await _svc(db).unshare(user.user_id, device_id, email)
    if result is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if result["grantee_id"] is not None:
        await manager.broadcast(result["grantee_id"], {"event": "device_unshared", "deviceId": device_id})
    return result["device"]
