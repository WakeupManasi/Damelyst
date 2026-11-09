from __future__ import annotations

import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.agents.workflow import run_route_analysis, stream_route_analysis
from app.api.dependencies import AgentDepsDep
from app.models.route import RouteAnalysisRequest, RouteAnalysisResult

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("/analyze", response_model=RouteAnalysisResult)
async def analyze_routes(
    payload: RouteAnalysisRequest, deps: AgentDepsDep
) -> RouteAnalysisResult:
    """Run the full agent workflow synchronously and return the final result."""
    final_state = await run_route_analysis(payload, deps)
    return RouteAnalysisResult(
        origin=final_state["origin"],
        destination=final_state["destination"],
        time_of_day=final_state["time_of_day"],
        routes=final_state["scored_routes"],
    )


@router.post("/analyze/stream")
async def analyze_routes_stream(payload: RouteAnalysisRequest, deps: AgentDepsDep):
    """
    Same workflow as /analyze, but streamed as Server-Sent Events: one
    `progress` event per completed agent step, followed by a final `result`
    event containing the full RouteAnalysisResult payload.
    """

    async def event_generator():
        async for event in stream_route_analysis(payload, deps):
            if event["event"] == "result":
                state = event["state"]
                result = RouteAnalysisResult(
                    origin=state["origin"],
                    destination=state["destination"],
                    time_of_day=state["time_of_day"],
                    routes=state["scored_routes"],
                )
                yield {
                    "event": "result",
                    "data": result.model_dump_json(),
                }
            else:
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {k: v for k, v in event.items() if k != "event"}, default=str
                    ),
                }

    return EventSourceResponse(event_generator())
