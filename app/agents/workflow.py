from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    fetch_relevant_incidents,
    fetch_route_candidates,
    generate_explanations,
    resolve_endpoints,
    score_candidates,
)
from app.agents.state import AgentDeps, AgentState
from app.models.route import RouteAnalysisRequest


def build_route_analysis_graph():
    graph = StateGraph(AgentState)

    graph.add_node("resolve_endpoints", resolve_endpoints)
    graph.add_node("fetch_route_candidates", fetch_route_candidates)
    graph.add_node("fetch_relevant_incidents", fetch_relevant_incidents)
    graph.add_node("score_candidates", score_candidates)
    graph.add_node("generate_explanations", generate_explanations)

    graph.add_edge(START, "resolve_endpoints")
    graph.add_edge("resolve_endpoints", "fetch_route_candidates")
    # Route fetching and incident fetching are independent of each other, but
    # LangGraph executes sequentially here for simplicity/predictable SSE
    # ordering; parallelize via add_edge fan-out if throughput matters later.
    graph.add_edge("fetch_route_candidates", "fetch_relevant_incidents")
    graph.add_edge("fetch_relevant_incidents", "score_candidates")
    graph.add_edge("score_candidates", "generate_explanations")
    graph.add_edge("generate_explanations", END)

    return graph.compile()


# Compiled once at import time; StateGraph.compile() is cheap and thread-safe to reuse.
route_analysis_graph = build_route_analysis_graph()


async def run_route_analysis(
    request: RouteAnalysisRequest, deps: AgentDeps
) -> AgentState:
    """Run the workflow to completion and return the final state."""
    initial_state: AgentState = {"request": request, "deps": deps, "progress": []}
    final_state = await route_analysis_graph.ainvoke(initial_state)
    return final_state


async def stream_route_analysis(
    request: RouteAnalysisRequest, deps: AgentDeps
) -> AsyncIterator[dict[str, Any]]:
    """
    Run the workflow exactly once, yielding one progress event per completed
    node (for SSE) and finishing with a single "result" event carrying the
    final state. Uses stream_mode="values" so the last yielded chunk already
    *is* the final state - no second, duplicate graph run.
    """
    initial_state: AgentState = {"request": request, "deps": deps, "progress": []}

    last_state: AgentState = initial_state
    seen_progress = 0
    async for state_value in route_analysis_graph.astream(initial_state, stream_mode="values"):
        last_state = state_value  # type: ignore[assignment]
        progress = state_value.get("progress", [])
        for entry in progress[seen_progress:]:
            yield {"event": "progress", **entry}
        seen_progress = len(progress)

    yield {"event": "result", "state": last_state}
