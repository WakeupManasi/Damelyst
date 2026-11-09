from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import geocode, health, incidents, route_analysis

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(geocode.router)
api_router.include_router(incidents.router)
api_router.include_router(route_analysis.router)
