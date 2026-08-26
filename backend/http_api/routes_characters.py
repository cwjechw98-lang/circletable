from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from http_api.helpers import room_loaded_payload


router = APIRouter()


@router.get("/api/characters")
async def list_characters(request: Request):
    runtime = get_runtime(request)
    return {"characters": runtime.repository.list_saved_profiles()}


@router.post("/api/characters")
async def create_character(request: Request, payload: dict):
    runtime = get_runtime(request)
    profile_id = runtime.repository.create_profile(payload, is_saved=True, system_provided=False)
    profile = runtime.repository.get_profile(profile_id)
    await runtime.manager.broadcast({"type": "participant_stats_updated", "inventory": runtime.repository.list_saved_profiles()})
    return profile


@router.patch("/api/characters/{character_id}")
async def update_character(request: Request, character_id: str, payload: dict):
    runtime = get_runtime(request)
    if not runtime.repository.get_profile(character_id):
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    runtime.repository.update_profile(character_id, payload)
    profile = runtime.repository.get_profile(character_id)
    await runtime.manager.broadcast({"type": "participant_stats_updated", "inventory": runtime.repository.list_saved_profiles()})
    return profile


@router.delete("/api/characters/{character_id}")
async def delete_character(request: Request, character_id: str):
    runtime = get_runtime(request)
    if not runtime.repository.get_profile(character_id):
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    runtime.repository.delete_profile(character_id)
    await runtime.manager.broadcast({"type": "participant_stats_updated", "inventory": runtime.repository.list_saved_profiles()})
    return {"ok": True}


@router.get("/api/rooms/{room_id}/inventory")
async def get_room_inventory(request: Request, room_id: str):
    runtime = get_runtime(request)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return {"participants": snapshot["participants"], "inventory": snapshot["inventory"], "teamPresets": snapshot["teamPresets"]}


@router.get("/api/team-presets")
async def list_team_presets(request: Request):
    runtime = get_runtime(request)
    return {"presets": runtime.repository.list_team_presets()}


@router.post("/api/team-presets")
async def create_team_preset(request: Request, payload: dict):
    runtime = get_runtime(request)
    room_id = payload.get("roomId") or runtime.repository.get_current_room_id()
    snapshot = runtime.repository.get_room_snapshot(room_id) if room_id else None
    participants = payload.get("participants") or (snapshot["participants"]["active"] if snapshot else [])
    if not participants:
        raise HTTPException(status_code=400, detail="Некого сохранять в состав")
    preset = runtime.repository.create_team_preset((payload.get("name") or "Новый состав").strip(), participants)
    await runtime.manager.broadcast({"type": "team_presets_updated", "teamPresets": runtime.repository.list_team_presets()})
    return preset


@router.delete("/api/team-presets/{preset_id}")
async def delete_team_preset(request: Request, preset_id: str):
    runtime = get_runtime(request)
    runtime.repository.delete_team_preset(preset_id)
    await runtime.manager.broadcast({"type": "team_presets_updated", "teamPresets": runtime.repository.list_team_presets()})
    return {"ok": True}


@router.post("/api/team-presets/{preset_id}/apply")
async def apply_team_preset(request: Request, preset_id: str, payload: dict):
    runtime = get_runtime(request)
    room_id = payload.get("roomId") or runtime.repository.get_current_room_id()
    if not room_id:
        raise HTTPException(status_code=400, detail="Комната не выбрана")
    if runtime.engine.running and runtime.engine.state != "paused":
        raise HTTPException(status_code=409, detail="Менять состав можно до старта или на паузе")
    created = runtime.repository.apply_team_preset(room_id, preset_id)
    session = runtime.repository.get_current_session(room_id)
    for participant in created:
        runtime.repository.add_room_event(room_id, session["id"] if session else None, "participant_added", participant)
    snapshot = runtime.repository.get_room_snapshot(room_id)
    await runtime.manager.broadcast({
        "type": "participant_roster_changed",
        "action": "состав применён",
        "participant": None,
        "participants": snapshot["participants"],
        "inventory": snapshot["inventory"],
    })
    await runtime.manager.broadcast(room_loaded_payload(runtime, snapshot, current_room_id=room_id))
    return snapshot
