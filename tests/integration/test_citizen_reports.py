"""Citizen-report persistence-agent and GenAI provider contract tests."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agent.citizen_reports import CitizenReportAgent
from api import main as api_main
from services.genai import OpenAICompatibleTriageProvider
from shared.enums import (
    CitizenReportCategory,
    ErrorCode,
    ReportSeverity,
    ReportTriageStatus,
)
from shared.errors import ReliefRouteError
from shared.models import (
    AuditEvent,
    CitizenReport,
    CitizenReportSubmission,
    CitizenReportTriage,
    LatLon,
    utc_now,
)


def submission(**overrides) -> CitizenReportSubmission:
    values = {
        "report_text": "Flood water is covering the road near the school.",
        "idempotency_key": "citizen-report-1",
        "ai_processing_consent": True,
    }
    return CitizenReportSubmission(**(values | overrides))


def triage_result(**overrides) -> CitizenReportTriage:
    values = {
        "category": CitizenReportCategory.FLOODING,
        "severity": ReportSeverity.HIGH,
        "summary": "A resident reports floodwater covering a road.",
        "confidence": 0.87,
        "needs_human_review": False,
        "provider": "test-provider",
        "model": "test-model",
    }
    return CitizenReportTriage(**(values | overrides))


class MemoryReportStore:
    def __init__(self) -> None:
        self.reports: dict[str, CitizenReport] = {}
        self.keys: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def create_or_get(self, request):
        async with self.lock:
            existing_id = self.keys.get(request.idempotency_key)
            if existing_id:
                report = self.reports[existing_id]
                if (
                    report.report_text != request.report_text
                    or (
                        request.observed_at is not None
                        and report.observed_at != request.observed_at
                    )
                    or report.location != request.location
                    or report.ai_processing_consent != request.ai_processing_consent
                ):
                    raise ReliefRouteError(ErrorCode.CONFLICT, "Idempotency key conflict.")
                return report

            status = (
                ReportTriageStatus.PENDING
                if request.ai_processing_consent
                else ReportTriageStatus.NOT_REQUESTED
            )
            report = CitizenReport(
                report_id="report-1",
                report_text=request.report_text,
                location=request.location,
                observed_at=request.observed_at or utc_now(),
                idempotency_key=request.idempotency_key,
                ai_processing_consent=request.ai_processing_consent,
                triage_status=status,
            )
            self.reports[report.report_id] = report
            self.keys[request.idempotency_key] = report.report_id
            return report

    async def get_report(self, report_id):
        return self.reports.get(report_id)

    async def claim_triage(self, report_id):
        async with self.lock:
            report = self.reports.get(report_id)
            if report is None or report.triage_status not in {
                ReportTriageStatus.PENDING,
                ReportTriageStatus.FAILED,
                ReportTriageStatus.UNAVAILABLE,
            }:
                return None
            claimed = report.model_copy(update={"triage_status": ReportTriageStatus.PROCESSING})
            self.reports[report_id] = claimed
            return claimed, "claim-token"

    async def finish_triage(self, report_id, *, claim_token, status, triage=None, error=None):
        assert claim_token == "claim-token"
        async with self.lock:
            report = self.reports[report_id]
            if report.triage_status != ReportTriageStatus.PROCESSING:
                raise ReliefRouteError(ErrorCode.CONFLICT, "Claim expired.")
            result = report.model_copy(
                update={
                    "triage_status": status,
                    "triage": triage,
                    "triage_error": error,
                }
            )
            self.reports[report_id] = result
            return result

    async def list_reports(self, **_kwargs):
        return list(self.reports.values())


class FakeTriageProvider:
    def __init__(self, result=None, error=None):
        self.result = result or triage_result()
        self.error = error
        self.calls = 0

    async def triage(self, report):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class MemoryAudit:
    def __init__(self):
        self.events: list[AuditEvent] = []

    async def append(self, event):
        if all(saved.event_id != event.event_id for saved in self.events):
            self.events.append(event)


def test_report_is_persisted_without_ai_consent():
    store = MemoryReportStore()
    provider = FakeTriageProvider()
    agent = CitizenReportAgent(store=store, triage_provider=provider)

    result = asyncio.run(agent.submit(submission(ai_processing_consent=False)))

    assert result.report_id in store.reports
    assert result.triage_status == ReportTriageStatus.NOT_REQUESTED
    assert result.triage is None
    assert provider.calls == 0


def test_ai_triage_is_advisory_and_always_requires_human_review():
    store = MemoryReportStore()
    provider = FakeTriageProvider(result=triage_result(needs_human_review=False))
    agent = CitizenReportAgent(store=store, triage_provider=provider)

    result = asyncio.run(agent.submit(submission()))

    assert result.triage_status == ReportTriageStatus.COMPLETE
    assert result.triage is not None
    assert result.triage.needs_human_review is True
    assert result.triage.severity == ReportSeverity.HIGH


def test_provider_unavailability_preserves_report_and_can_be_retried():
    store = MemoryReportStore()
    provider = FakeTriageProvider(
        error=ReliefRouteError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "GenAI provider is unavailable.",
            retryable=True,
        )
    )
    agent = CitizenReportAgent(store=store, triage_provider=provider)

    first = asyncio.run(agent.submit(submission()))
    assert first.triage_status == ReportTriageStatus.UNAVAILABLE
    assert first.triage is None

    provider.error = None
    retried = asyncio.run(agent.triage(first.report_id))
    assert retried.triage_status == ReportTriageStatus.COMPLETE
    assert provider.calls == 2


def test_report_idempotency_prevents_duplicate_triage_and_audit():
    store = MemoryReportStore()
    provider = FakeTriageProvider()
    audit = MemoryAudit()
    agent = CitizenReportAgent(store=store, triage_provider=provider, audit=audit)

    request = submission()
    first, repeated = asyncio.run(_submit_twice(agent, request, request))

    assert first.report_id == repeated.report_id
    assert provider.calls == 1
    assert sum(event.action == "CITIZEN_REPORT_RECEIVED" for event in audit.events) == 1


async def _submit_twice(agent, first, second):
    results = await asyncio.gather(agent.submit(first), agent.submit(second))
    return results[0], results[1]


def test_same_idempotency_key_with_different_report_is_rejected():
    store = MemoryReportStore()
    agent = CitizenReportAgent(store=store, triage_provider=FakeTriageProvider())

    async def submit_conflict():
        await agent.submit(submission())
        await agent.submit(submission(report_text="A different report for this same key."))

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(submit_conflict())
    assert error.value.error.code == ErrorCode.CONFLICT


@pytest.mark.parametrize(
    ("status_code", "body", "error_code"),
    [
        (401, {"error": "unauthorized"}, ErrorCode.UPSTREAM_AUTH_FAILED),
        (429, {"error": "rate limited"}, ErrorCode.UPSTREAM_RATE_LIMITED),
        (503, {"error": "unavailable"}, ErrorCode.UPSTREAM_UNAVAILABLE),
    ],
)
def test_genai_provider_surfaces_provider_errors(status_code, body, error_code):
    async def call():
        transport = httpx.MockTransport(lambda _request: httpx.Response(status_code, json=body))
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleTriageProvider(
                api_key="test-key",
                model="test-model",
                client=client,
            )
            report = CitizenReport(
                report_id="report-1",
                report_text="Flooding along the road near town.",
                location=LatLon(latitude=12.7, longitude=77.6),
                observed_at=utc_now(),
                idempotency_key="report-1",
            )
            return await provider.triage(report)

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(call())
    assert error.value.error.code == error_code


def test_genai_provider_validates_structured_output_and_does_not_send_location():
    observed = {}

    def handler(request):
        observed["payload"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "category": "FLOODING",
                                    "severity": "HIGH",
                                    "summary": "A resident reports flooding.",
                                    "confidence": 0.9,
                                }
                            )
                        }
                    }
                ]
            },
        )

    async def call():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleTriageProvider(
                api_key="test-key",
                model="test-model",
                base_url="https://llm.example/v1/",
                client=client,
            )
            report = CitizenReport(
                report_id="report-1",
                report_text="Flooding along the road near town.",
                location=LatLon(latitude=12.7, longitude=77.6),
                observed_at=utc_now(),
                idempotency_key="report-1",
            )
            return await provider.triage(report)

    result = asyncio.run(call())

    assert result.needs_human_review is True
    assert result.provider == "openai_compatible"
    assert observed["payload"]["response_format"] == {"type": "json_object"}
    user_content = observed["payload"]["messages"][1]["content"]
    assert "location" not in user_content


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        json.dumps(
            {
                "category": "UNSUPPORTED",
                "severity": "HIGH",
                "summary": "Invalid category.",
                "confidence": 0.9,
            }
        ),
        json.dumps(
            {
                "category": "FLOODING",
                "severity": "HIGH",
                "summary": "Unexpected output fields are rejected.",
                "confidence": 0.9,
                "dispatch_approved": True,
            }
        ),
    ],
)
def test_genai_provider_rejects_malformed_or_unsupported_triage(content):
    async def call():
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleTriageProvider(
                api_key="test-key",
                model="test-model",
                client=client,
            )
            return await provider.triage(
                CitizenReport(
                    report_id="report-1",
                    report_text="Flooding along the road near town.",
                    observed_at=utc_now(),
                    idempotency_key="report-1",
                )
            )

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(call())
    assert error.value.error.code == ErrorCode.INVALID_UPSTREAM_RESPONSE


def test_genai_provider_rejects_unconfigured_credentials():
    async def call():
        provider = OpenAICompatibleTriageProvider(api_key="", model="")
        report = CitizenReport(
            report_id="report-1",
            report_text="Flooding along the road near town.",
            observed_at=utc_now(),
            idempotency_key="report-1",
        )
        return await provider.triage(report)

    with pytest.raises(ReliefRouteError) as error:
        asyncio.run(call())
    assert error.value.error.code == ErrorCode.UPSTREAM_UNAVAILABLE


def test_citizen_report_api_submit_list_get_and_retriage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    store = MemoryReportStore()
    provider = FakeTriageProvider()
    agent = CitizenReportAgent(store=store, triage_provider=provider)

    with TestClient(api_main.app) as client:
        api_main.app.state.citizen_report_store = store
        api_main.app.state.citizen_report_agent = agent

        created = client.post(
            "/citizen-reports",
            json={
                "report_text": "Flood water is covering the road near the school.",
                "idempotency_key": "api-report-1",
                "ai_processing_consent": True,
            },
        )
        assert created.status_code == 201, created.text
        report_id = created.json()["report_id"]
        assert created.json()["triage_status"] == "COMPLETE"
        assert created.json()["triage"]["needs_human_review"] is True

        listed = client.get("/citizen-reports?limit=10")
        fetched = client.get(f"/citizen-reports/{report_id}")
        retriaged = client.post(f"/citizen-reports/{report_id}/triage")
        missing = client.get("/citizen-reports/missing")

    assert listed.status_code == 200
    assert listed.json()[0]["report_id"] == report_id
    assert fetched.status_code == 200
    assert retriaged.status_code == 200
    assert provider.calls == 1
    assert missing.status_code == 404


def test_citizen_report_api_rejects_invalid_submission(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    with TestClient(api_main.app) as client:
        api_main.app.state.citizen_report_store = MemoryReportStore()
        api_main.app.state.citizen_report_agent = CitizenReportAgent(
            store=api_main.app.state.citizen_report_store,
            triage_provider=FakeTriageProvider(),
        )
        response = client.post(
            "/citizen-reports",
            json={
                "report_text": "short",
                "idempotency_key": "",
            },
        )
    assert response.status_code == 422
