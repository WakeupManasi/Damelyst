from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DamelystError(Exception):
    """Base class for all domain-level errors."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GeocodingError(DamelystError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "geocoding_failed"


class GeocodeNotFoundError(DamelystError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "geocode_not_found"


class RoutingError(DamelystError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "routing_failed"


class NoRoutesFoundError(DamelystError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "no_routes_found"


class LLMError(DamelystError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "llm_failed"


class IncidentNotFoundError(DamelystError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "incident_not_found"


class UpstreamConfigError(DamelystError):
    """Raised when a required upstream API key/config is missing."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "upstream_not_configured"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DamelystError)
    async def _handle_damelyst_error(request: Request, exc: DamelystError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )
