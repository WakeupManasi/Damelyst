from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.agents.state import AgentDeps
from app.core.config import Settings, get_settings
from app.repositories.memory import InMemoryIncidentRepository, InMemoryRouteCache
from app.repositories.protocols import IncidentRepository, RouteCacheRepository
from app.services.geocoding import GeoapifyClient
from app.services.llm import build_explainer
from app.services.routing import OpenRouteServiceClient

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Reuses the single AsyncClient created in the app lifespan (see main.py)."""
    return request.app.state.http_client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def get_incident_repository(request: Request) -> IncidentRepository:
    return request.app.state.incident_repo


IncidentRepoDep = Annotated[IncidentRepository, Depends(get_incident_repository)]


def get_route_cache(request: Request) -> RouteCacheRepository:
    return request.app.state.route_cache


RouteCacheDep = Annotated[RouteCacheRepository, Depends(get_route_cache)]


def get_geocoder(client: HttpClientDep, settings: SettingsDep) -> GeoapifyClient:
    return GeoapifyClient(client, settings)


def get_router_client(client: HttpClientDep, settings: SettingsDep) -> OpenRouteServiceClient:
    return OpenRouteServiceClient(client, settings)


def get_agent_deps(
    client: HttpClientDep,
    settings: SettingsDep,
    incident_repo: IncidentRepoDep,
) -> AgentDeps:
    return AgentDeps(
        geocoder=GeoapifyClient(client, settings),
        router=OpenRouteServiceClient(client, settings),
        incident_repo=incident_repo,
        explainer=build_explainer(client, settings),
    )


AgentDepsDep = Annotated[AgentDeps, Depends(get_agent_deps)]


def create_default_repositories() -> tuple[InMemoryIncidentRepository, InMemoryRouteCache]:
    """Factory used at app startup; keeps repo construction in one place."""
    return InMemoryIncidentRepository(), InMemoryRouteCache()
