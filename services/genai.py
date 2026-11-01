"""OpenAI-compatible GenAI provider for citizen-report triage."""

import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.enums import (
    CitizenReportCategory,
    ErrorCode,
    ReportSeverity,
)
from shared.errors import ReliefRouteError
from shared.models import CitizenReport, CitizenReportTriage


class _TriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CitizenReportCategory
    severity: ReportSeverity
    summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)


class OpenAICompatibleTriageProvider:
    """Request a constrained, evidence-based advisory classification."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY")
        self.model = model if model is not None else os.getenv("LLM_MODEL")
        self.base_url = (
            base_url if base_url is not None else os.getenv("LLM_BASE_URL")
        ) or "https://api.openai.com/v1"
        self.base_url = self.base_url.rstrip("/")
        self.client = client
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def triage(self, report: CitizenReport) -> CitizenReportTriage:
        if not self.configured:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "GenAI triage is not configured.",
                provider="genai",
                details={"required_configuration": ["LLM_API_KEY", "LLM_MODEL"]},
            )

        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Classify the citizen incident report using only facts in "
                        "the supplied report. Return one JSON object with category, "
                        "severity, summary, confidence. category must be one of "
                        "FLOODING, ROAD_BLOCKAGE, INFRASTRUCTURE_DAMAGE, "
                        "MEDICAL_EMERGENCY, SUPPLY_NEED, OTHER. severity must be "
                        "one of INFORMATIONAL, MODERATE, HIGH, CRITICAL. Keep the "
                        "summary concise and distinguish reported claims from "
                        "verified facts. Do not invent locations, injuries, causes, "
                        "or response actions. This is advisory triage only; never "
                        "approve dispatch or claim an emergency was verified."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"report": report.report_text}),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self.client is not None:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
        except httpx.TimeoutException as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_TIMEOUT,
                "GenAI provider timed out during report triage.",
                retryable=True,
                provider="genai",
            ) from exc
        except httpx.RequestError as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not connect to the GenAI provider.",
                retryable=True,
                provider="genai",
            ) from exc

        if response.status_code in {401, 403}:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_AUTH_FAILED,
                "GenAI provider rejected the configured credentials.",
                provider="genai",
            )
        if response.status_code == 429:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_RATE_LIMITED,
                "GenAI provider rate-limited the triage request.",
                retryable=True,
                provider="genai",
            )
        if response.status_code >= 500:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "GenAI provider is temporarily unavailable.",
                retryable=True,
                provider="genai",
                details={"status_code": response.status_code},
            )
        if response.is_error:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "GenAI provider rejected the triage request.",
                provider="genai",
                details={"status_code": response.status_code},
            )

        parsed_response = self._parse_response(response)
        try:
            output = _TriageOutput.model_validate(parsed_response)
        except ValidationError as exc:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "GenAI returned triage fields outside the supported contract.",
                provider="genai",
            ) from exc

        return CitizenReportTriage(
            **output.model_dump(),
            needs_human_review=True,
            generated_at=datetime.now(UTC),
            provider="openai_compatible",
            model=self.model or "unconfigured",
        )

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "GenAI returned an invalid triage response.",
                provider="genai",
            ) from exc
        if not isinstance(result, dict):
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "GenAI triage response must be a JSON object.",
                provider="genai",
            )
        return result
