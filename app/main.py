from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import create_default_repositories
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.errors import register_exception_handlers

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    app.state.http_client = httpx.AsyncClient()
    app.state.incident_repo, app.state.route_cache = create_default_repositories()

    logger.info(
        "Damelyst backend starting | env=%s | ors=%s | geoapify=%s | llm=%s(%s)",
        settings.app_env,
        settings.has_live_ors,
        settings.has_live_geoapify,
        settings.has_live_llm,
        settings.llm_provider,
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logger.info("Damelyst backend shut down cleanly.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Damelyst",
        description=(
            "Pedestrian route decision-support API. Compares walking routes on "
            "lighting, activity, visibility, main-road quality, oversight, "
            "emergency proximity and verified incident signals."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    return app


app = create_app()
