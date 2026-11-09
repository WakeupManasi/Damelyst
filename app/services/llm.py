from __future__ import annotations

from typing import Protocol

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.common import ScoreBreakdown
from app.services.errors import LLMError

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are Damelyst's route-explanation assistant. You explain, in 2-4 concise "
    "sentences, why a walking route received the safety/quality score it did. "
    "You MUST ground every claim strictly in the numeric dimension scores and "
    "rationales provided to you - never invent facts, landmarks, or incidents "
    "that are not in the provided data. If information is uncertain or "
    "heuristic, say so plainly. Do not give legal or medical advice. Write in "
    "plain, direct language for a pedestrian deciding which way to walk."
)


class Explainer(Protocol):
    async def explain(self, route_label: str, score: ScoreBreakdown, incident_count: int) -> str: ...


def _build_user_prompt(route_label: str, score: ScoreBreakdown, incident_count: int) -> str:
    lines = [
        f"Route: {route_label}",
        f"Time of day: {score.time_of_day.value}",
        f"Overall score: {score.overall:.1f}/100",
        f"Nearby incident reports considered: {incident_count}",
        "Dimension breakdown (value/100, weight, rationale):",
    ]
    for d in score.dimensions:
        lines.append(f"- {d.dimension.value}: {d.value:.1f} (weight {d.weight:.2f}) - {d.rationale}")
    lines.append(
        "Write a short, grounded explanation of this score for the pedestrian. "
        "Mention the 1-2 strongest and 1-2 weakest dimensions by name."
    )
    return "\n".join(lines)


class OpenAIExplainer:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=3),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def explain(self, route_label: str, score: ScoreBreakdown, incident_count: int) -> str:
        url = f"{self._settings.openai_base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self._settings.openai_api_key}"}
        payload = {
            "model": self._settings.openai_model,
            "temperature": 0.3,
            "max_tokens": 220,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(route_label, score, incident_count)},
            ],
        }
        try:
            response = await self._client.post(
                url, json=payload, headers=headers, timeout=self._settings.http_timeout_seconds
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            logger.exception("OpenAI explanation request failed")
            raise LLMError(f"OpenAI request failed: {exc}") from exc


class GeminiExplainer:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    @retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, max=3),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def explain(self, route_label: str, score: ScoreBreakdown, incident_count: int) -> str:
        model = self._settings.gemini_model
        url = f"{self._settings.gemini_base_url}/models/{model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": _SYSTEM_PROMPT
                            + "\n\n"
                            + _build_user_prompt(route_label, score, incident_count)
                        }
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 220},
        }
        try:
            response = await self._client.post(
                url,
                params={"key": self._settings.gemini_api_key},
                json=payload,
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except httpx.HTTPError as exc:
            logger.exception("Gemini explanation request failed")
            raise LLMError(f"Gemini request failed: {exc}") from exc


class DeterministicFallbackExplainer:
    """
    No-API-key fallback so the service is runnable end-to-end without live LLM
    credentials. Produces a grounded, template-based explanation directly from
    the score breakdown - useful for local dev, tests, and CI.
    """

    async def explain(self, route_label: str, score: ScoreBreakdown, incident_count: int) -> str:
        ranked = sorted(score.dimensions, key=lambda d: d.value, reverse=True)
        strongest = ranked[:2]
        weakest = list(reversed(ranked))[:2]
        strong_txt = ", ".join(f"{d.dimension.value} ({d.value:.0f}/100)" for d in strongest)
        weak_txt = ", ".join(f"{d.dimension.value} ({d.value:.0f}/100)" for d in weakest)
        incident_txt = (
            f"{incident_count} nearby incident report(s) were factored in."
            if incident_count
            else "No nearby incident reports were found."
        )
        return (
            f"{route_label} scores {score.overall:.0f}/100 for {score.time_of_day.value}. "
            f"Strongest factors: {strong_txt}. Weaker factors: {weak_txt}. {incident_txt}"
        )


def build_explainer(client: httpx.AsyncClient, settings: Settings) -> Explainer:
    if not settings.has_live_llm:
        return DeterministicFallbackExplainer()
    if settings.llm_provider == "gemini":
        return GeminiExplainer(client, settings)
    return OpenAIExplainer(client, settings)
