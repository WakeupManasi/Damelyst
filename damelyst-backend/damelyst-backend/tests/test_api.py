from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import get_settings


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ORS_API_KEY", "test-ors-key")
    monkeypatch.setenv("GEOAPIFY_API_KEY", "test-geoapify-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "changeme")  # keep LLM in deterministic-fallback mode
    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["upstreams"]["openrouteservice"] is True
    assert body["upstreams"]["llm"] is False  # falls back to deterministic explainer


def test_create_and_list_incident(client: TestClient):
    create_resp = client.post(
        "/incidents",
        json={
            "location": {"lon": 0.001, "lat": 0.001},
            "incident_type": "poor_lighting",
            "description": "Broken streetlight for two weeks.",
        },
    )
    assert create_resp.status_code == 201
    incident_id = create_resp.json()["incident_id"]

    get_resp = client.get(f"/incidents/{incident_id}")
    assert get_resp.status_code == 200

    nearby_resp = client.get("/incidents", params={"lat": 0.0, "lon": 0.0, "radius_m": 500})
    assert nearby_resp.status_code == 200
    assert any(i["incident_id"] == incident_id for i in nearby_resp.json())


def test_get_unknown_incident_returns_404(client: TestClient):
    response = client.get("/incidents/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"] == "incident_not_found"


_ORS_RESPONSE = {
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [0.0, 0.005], [0.0, 0.01]],
            },
            "properties": {
                "summary": {"distance": 1100.0, "duration": 800.0},
                "segments": [
                    {
                        "distance": 1100.0,
                        "duration": 800.0,
                        "steps": [
                            {
                                "distance": 1100.0,
                                "duration": 800.0,
                                "name": "Main Avenue",
                                "way_points": [0, 2],
                            }
                        ],
                    }
                ],
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0], [0.003, 0.003], [0.0, 0.01]],
            },
            "properties": {
                "summary": {"distance": 1400.0, "duration": 950.0},
                "segments": [
                    {
                        "distance": 1400.0,
                        "duration": 950.0,
                        "steps": [
                            {
                                "distance": 1400.0,
                                "duration": 950.0,
                                "name": "Backalley Path",
                                "way_points": [0, 2],
                            }
                        ],
                    }
                ],
            },
        },
    ]
}


@respx.mock
def test_analyze_routes_end_to_end_with_mocked_ors(client: TestClient):
    respx.post(
        "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"
    ).mock(return_value=Response(200, json=_ORS_RESPONSE))

    payload = {
        "origin": {"lon": 0.0, "lat": 0.0},
        "destination": {"lon": 0.0, "lat": 0.01},
        "max_alternatives": 2,
    }
    response = client.post("/routes/analyze", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert len(body["routes"]) == 2
    assert body["recommended_route_id"] is not None
    # Main-Avenue route should be scored at least as well as the back-alley one.
    scores = {r["candidate"]["route_id"]: r["score"]["overall"] for r in body["routes"]}
    main_route = next(
        r for r in body["routes"] if r["candidate"]["segments"][0]["street_name"] == "Main Avenue"
    )
    other_route = next(
        r for r in body["routes"] if r["candidate"]["segments"][0]["street_name"] != "Main Avenue"
    )
    assert scores[main_route["candidate"]["route_id"]] >= scores[other_route["candidate"]["route_id"]]
    assert main_route["explanation"]
