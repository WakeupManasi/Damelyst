# D Damelyst: A Multi-Agent GeoAI System for Real-Time Safer Route Intelligence

Damelyst compares candidate walking routes between two points and scores each
one on seven dimensions — **lighting, activity, visibility, main-road
quality, oversight, emergency proximity,** and **verified incident
history** — then asks an LLM to explain the score in plain language, grounded
strictly in the computed numbers.

A [LangGraph](https://langchain-ai.github.io/langgraph/) agent orchestrates
the pipeline (geocode → fetch routes → fetch incidents → score → explain),
streaming its progress live over **Server-Sent Events**.

## Stack

- Python 3.12, FastAPI, Pydantic v2, Uvicorn
- LangGraph for the agent workflow
- HTTPX for all outbound HTTP
- **OpenRouteService** — walking directions / alternative routes
- **Geoapify** — free-text address geocoding
- **OpenAI or Gemini** — grounded score explanations (optional — falls back
  to a deterministic template explainer if no key is configured, so the
  whole thing runs out of the box)
- Server-Sent Events (`sse-starlette`) for live agent progress
- `uv`, Pytest, Ruff

No database, auth provider, Redis, or Celery. Storage is an **async
in-memory repository** behind a `Protocol` (`app/repositories/protocols.py`),
so swapping in Postgres/PostGIS later means writing one new class — no
caller changes.

## Project layout

```
damelyst-backend/
├── app/
│   ├── main.py                    # FastAPI app, lifespan, CORS, error handlers
│   ├── core/                      # settings (env), logging
│   ├── models/                    # Pydantic models: common, route, incident, user
│   ├── agents/                    # LangGraph state, nodes, compiled workflow
│   ├── repositories/              # Protocol + in-memory implementation
│   ├── services/                  # ORS, Geoapify, LLM, scoring, geometry, errors
│   └── api/                       # DI, routers: health, geocode, incidents, route_analysis
├── tests/                         # pytest, incl. a fully mocked end-to-end test
├── .env.example
├── pyproject.toml
└── Dockerfile
```

## Setup

```bash
cd damelyst-backend
uv venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

cp .env.example .env
# then fill in ORS_API_KEY / GEOAPIFY_API_KEY / OPENAI_API_KEY (or GEMINI_API_KEY)
```

You can leave any of the three third-party keys as `changeme`:

- No `GEOAPIFY_API_KEY` → geocoding endpoints return `503`, but requests that
  pass raw `{lon, lat}` coordinates instead of free-text addresses work fine.
- No `ORS_API_KEY` → route analysis returns `503` (this is the one key you
  actually need for the core feature).
- No LLM key → explanations still generate, using a deterministic,
  score-grounded template instead of an LLM call. Nothing breaks.

## Run

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for interactive Swagger UI.

### Try it

```bash
# Health / which upstreams are configured
curl http://localhost:8000/health

# Geocode a free-text address
curl "http://localhost:8000/geocode?q=Times+Square,+New+York"

# Report an incident (no auth in this prototype)
curl -X POST http://localhost:8000/incidents \
  -H "Content-Type: application/json" \
  -d '{"location":{"lon":-73.9857,"lat":40.7484},"incident_type":"poor_lighting","description":"Streetlight out for two weeks."}'

# Analyze routes (synchronous)
curl -X POST http://localhost:8000/routes/analyze \
  -H "Content-Type: application/json" \
  -d '{"origin":{"lon":-73.9857,"lat":40.7484},"destination":{"lon":-73.9776,"lat":40.7527},"max_alternatives":3}'

# Analyze routes, streamed live via SSE
curl -N -X POST http://localhost:8000/routes/analyze/stream \
  -H "Content-Type: application/json" \
  -d '{"origin":{"lon":-73.9857,"lat":40.7484},"destination":{"lon":-73.9776,"lat":40.7527}}'
```

The SSE stream emits one `progress` event per agent step
(`resolve_endpoints`, `fetch_route_candidates`, `fetch_relevant_incidents`,
`score_candidates`, `generate_explanations`), then a final `result` event
carrying the full `RouteAnalysisResult` JSON.

### Run tests / lint

```bash
pytest
ruff check .
```

`tests/test_api.py` includes a fully mocked end-to-end run of
`/routes/analyze` (ORS response mocked via `respx`; no live network or API
keys required), plus unit tests for geometry, scoring, and the in-memory
repositories.

### Docker

```bash
docker build -t damelyst-backend .
docker run --env-file .env -p 8000:8000 damelyst-backend
```

## How scoring works

`app/services/scoring.py` computes a weighted composite (`DEFAULT_WEIGHTS`)
from seven `DimensionScore`s per route:

- **lighting, activity, visibility, oversight** — come from
  `InfrastructureSignalProvider`, a `Protocol` with one default
  implementation (`HeuristicInfrastructureSignalProvider`) that derives a
  transparent estimate from main-road coverage and time-of-day. It's
  intentionally the most "prototype" part of the system and the first thing
  to replace.
- **main_road_quality** — % of route distance on segments ORS/your data
  classifies as a main road.
- **emergency_proximity** — proxy for reachability by responders/help;
  currently derived the same way as main-road quality.
- **incident_history** — the one dimension backed by *real* data: every
  report within 60m of the route corridor, weighted by recency (90-day
  half-life) and verification status (`officially_verified` counts most,
  `unverified` least, `rejected` counts zero).

Clients can override dimension weights per-request via
`dimension_weights` in the `/routes/analyze` body (values are renormalized,
so partial overrides are safe).

## What I'd extend first

1. **Real infrastructure signals.** Swap
   `HeuristicInfrastructureSignalProvider` for real data: a streetlight GIS
   layer (lighting), OSM/Overture POI density (activity, oversight), a CCTV
   or business-frontage registry (oversight), and actual EMS/police station
   locations (emergency proximity). The `Protocol` boundary means this is a
   pure swap, no changes to `score_route` or the agent nodes.
2. **A real database behind `IncidentRepository`.** The in-memory store
   works for a prototype but loses data on restart and doesn't scale past
   one process. Implement the same `Protocol` against Postgres + PostGIS
   (`ST_DWithin` instead of the Python haversine loop in
   `list_near`) — everything else is untouched.
3. **Incident verification workflow + light auth.** Right now every report
   starts `unverified` with no way to move it forward and no reporter
   identity beyond an optional opaque string. This is the natural next
   feature once you add a real user/session layer — `app/models/user.py`
   already sketches the per-user preference shape (`UserRoutingPreferences`)
   to build on.
4. **Parallelize independent LangGraph nodes.** `fetch_route_candidates` and
   `fetch_relevant_incidents` don't depend on each other but currently run
   sequentially for simpler SSE ordering — fan them out with a parallel
   edge once route-analysis latency matters more than event ordering.
5. **Route-level caching.** `RouteCacheRepository` is defined and
   implemented (`InMemoryRouteCache`) but not yet wired into
   `/routes/analyze` — obvious win for repeat origin/destination/time-bucket
   queries before you add a real cache backend.
