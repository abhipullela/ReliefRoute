from agent.intelligence import validate_emergency_report
from shared.models import (
    ExtractedEmergencyReport,
    ExtractedNeed,
)
from shared.enums import EmergencyUrgency, VerificationStatus


def test_valid_emergency_report():
    report = ExtractedEmergencyReport(
        report_id="TEST001",
        incident_type="flooding",
        location_description="Village",
        needs=[
            ExtractedNeed(
                commodity="drinking water",
                quantity=100,
                unit="litres",
            )
        ],
        reported_urgency=EmergencyUrgency.HIGH,
        verification_status=VerificationStatus.PENDING,
    )

    result = validate_emergency_report(report)

    assert result.structurally_valid is True
    assert result.validation_issues == []


def test_missing_incident_type():
    report = ExtractedEmergencyReport(
        report_id="TEST002",
        location_description="Village",
        needs=[
            ExtractedNeed(commodity="food")
        ],
    )

    result = validate_emergency_report(report)

    assert result.structurally_valid is False
    assert "incident_type" in result.clarification_fields


def test_missing_location():
    report = ExtractedEmergencyReport(
        report_id="TEST003",
        incident_type="flooding",
        needs=[
            ExtractedNeed(commodity="food")
        ],
    )

    result = validate_emergency_report(report)

    assert result.structurally_valid is False
    assert "location" in result.clarification_fields


def test_unspecified_quantity():
    report = ExtractedEmergencyReport(
        report_id="TEST004",
        incident_type="flooding",
        location_description="Village",
        needs=[
            ExtractedNeed(commodity="food")
        ],
    )

    result = validate_emergency_report(report)

    assert result.structurally_valid is True
    assert "quantity_for_food" in result.clarification_fields
import pytest
from unittest.mock import AsyncMock

import agent.intelligence as intelligence

from shared.models import CitizenReport, LatLon


class MockResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": """
                        {
                            "incident_type": "flooding",
                            "location_description": "Village",
                            "coordinates": null,
                            "people_affected": null,
                            "needs": [
                                {
                                    "commodity": "drinking water",
                                    "quantity": null,
                                    "unit": null,
                                    "evidence": ["Water is needed"]
                                }
                            ],
                            "reported_conditions": ["severe flooding"],
                            "reported_urgency": "HIGH",
                            "missing_information": ["exact coordinates"],
                            "extraction_confidence": 0.9,
                            "verification_status": "VERIFIED"
                        }
                        """
                    }
                }
            ]
        }


class MockClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, *args, **kwargs):
        return MockResponse()


@pytest.mark.asyncio
async def test_extract_emergency_report(monkeypatch):
    monkeypatch.setattr(
        intelligence.httpx,
        "AsyncClient",
        lambda **kwargs: MockClient(),
    )

    report = CitizenReport(
        report_id="TEST005",
        raw_text="Severe flooding. We need drinking water.",
        raw_location_text="Village",
    )

    result = await intelligence.extract_emergency_report(report)

    assert result.report_id == "TEST005"
    assert result.incident_type == "flooding"
    assert result.verification_status.value == "PENDING"
    assert result.needs[0].commodity == "drinking water"