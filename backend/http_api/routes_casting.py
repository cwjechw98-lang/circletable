from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from http_api.deps import get_runtime
from http_api.helpers import broadcast_custom_specialties, specialty_label_from_hint


router = APIRouter()


@router.post("/api/casting/suggest")
async def suggest_casting(request: Request, payload: dict):
    runtime = get_runtime(request)
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Сначала введите тему или вопрос")

    providers = await runtime.providers_payload()
    active_participants = payload.get("activeParticipants")
    helper_provider = payload.get("provider")
    helper_model = payload.get("model")
    curated_recall = ""
    try:
        recent_insights = runtime.repository.list_session_insights(limit=72)
        relevant_insights = runtime.select_relevant_session_insights_fn(
            recent_insights,
            topic=topic,
            participants=active_participants,
            observer_provider=helper_provider,
            observer_model=helper_model,
            missing_expert_hint=payload.get("missingExpertHint"),
            audience="casting",
            limit=3,
        )
        curated_recall = runtime.format_insight_recall_fn(
            relevant_insights,
            audience="casting",
            limit=1400,
        )
    except Exception:
        curated_recall = ""
    return await runtime.suggest_characters_fn(
        topic=topic,
        count=payload.get("count"),
        providers_payload=providers,
        mode=payload.get("mode") or "full",
        provider_name=helper_provider,
        model=helper_model,
        room_summary=payload.get("roomSummary"),
        session_chronicle=payload.get("sessionChronicle"),
        latest_round_summary=payload.get("latestRoundSummary"),
        active_participants=active_participants,
        missing_expert_hint=payload.get("missingExpertHint"),
        custom_specialties=runtime.repository.list_custom_specialties(),
        curated_recall=curated_recall,
    )


@router.get("/api/specialties")
async def list_custom_specialties(request: Request):
    runtime = get_runtime(request)
    return {
        "specialties": runtime.repository.list_custom_specialties(),
        "customSpecialtyGroups": runtime.repository.list_custom_specialty_groups(),
    }


@router.post("/api/specialties")
async def create_custom_specialty(request: Request, payload: dict):
    runtime = get_runtime(request)
    label = str(payload.get("label") or "").strip()
    if not label:
        label = specialty_label_from_hint(payload.get("sourceHint"))
    if not label:
        raise HTTPException(status_code=400, detail="Название экспертизы не может быть пустым")
    specialty = runtime.repository.create_custom_specialty(
        label,
        group_label=payload.get("groupLabel") or payload.get("group_label") or "Кастомные оптики",
        description=payload.get("description") or payload.get("sourceHint") or "",
    )
    groups = runtime.repository.list_custom_specialty_groups()
    await broadcast_custom_specialties(runtime)
    return {"specialty": specialty, "customSpecialtyGroups": groups}


@router.patch("/api/specialties/{specialty_id}")
async def update_custom_specialty(request: Request, specialty_id: str, payload: dict):
    runtime = get_runtime(request)
    specialty = runtime.repository.update_custom_specialty(specialty_id, payload)
    if not specialty:
        raise HTTPException(status_code=404, detail="Экспертиза не найдена")
    groups = runtime.repository.list_custom_specialty_groups()
    await broadcast_custom_specialties(runtime)
    return {"specialty": specialty, "customSpecialtyGroups": groups}


@router.delete("/api/specialties/{specialty_id}")
async def delete_custom_specialty(request: Request, specialty_id: str):
    runtime = get_runtime(request)
    result = runtime.repository.delete_custom_specialty(specialty_id)
    if result == "missing":
        raise HTTPException(status_code=404, detail="Экспертиза не найдена")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Экспертиза уже используется персонажем или составом")
    groups = runtime.repository.list_custom_specialty_groups()
    await broadcast_custom_specialties(runtime)
    return {"ok": True, "customSpecialtyGroups": groups}
