from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import SettingsDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: SettingsDep) -> dict:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "upstreams": {
            "openrouteservice": settings.has_live_ors,
            "geoapify": settings.has_live_geoapify,
            "llm": settings.has_live_llm,
            "llm_provider": settings.llm_provider,
        },
    }
