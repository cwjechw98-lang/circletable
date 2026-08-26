from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime


router = APIRouter()


@router.get("/api/lab/profiles")
async def list_lab_profiles(request: Request):
    runtime = get_runtime(request)
    return {"dossiers": runtime.repository.list_lab_dossiers()}


@router.get("/api/lab/profiles/{profile_id}")
async def get_lab_profile(request: Request, profile_id: str):
    runtime = get_runtime(request)
    dossier = runtime.repository.get_lab_dossier(profile_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Персонаж не найден")
    return dossier
