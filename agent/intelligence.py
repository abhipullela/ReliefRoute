import json

import httpx

from agent.config import settings
from shared.enums import VerificationStatus
from shared.models import CitizenReport, ExtractedEmergencyReport, ReportValidationResult

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


async def test_groq_connection() -> str:
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.groq_model,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: ReliefRoute AI connected!",
            }
        ],
        "temperature": 0,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    return result["choices"][0]["message"]["content"]


async def extract_emergency_report(
    report: CitizenReport,
) -> ExtractedEmergencyReport:

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = """
    You are an emergency report information extraction assistant.

    Extract information from citizen emergency reports.
    Return ONLY valid JSON. Do not include markdown or explanations.

    Rules:
    1. Never invent information, quantities, locations, or coordinates.
    2. Extract only information explicitly stated or clearly supported.
    3. Do not convert families into people.
    4. If the report explicitly mentions a number of families or households,
   extract that number into affected_households.

    5. If the report mentions families but not individual people,
   keep people_affected as null.

    6. Do not use the number of affected households as the quantity
   of drinking water, food, or any other commodity.
    7. If quantity is unknown, use null.
    8. Coordinates must remain null unless explicitly provided.
    9. Urgency represents what the citizen reports, not verified severity.
    10. Verification status must always be PENDING.
    11. List missing information that would help responders.
    12. reported_urgency MUST be exactly one of:
   CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN.
   Never use words like URGENT or EMERGENCY.

    Use this JSON structure:
    {
        "incident_type": null,
        "location_description": null,
        "coordinates": null,
        "people_affected": null,
        "affected_households": null,
        "needs": [],
        "reported_conditions": [],
        "reported_urgency": "UNKNOWN",
        "missing_information": [],
        "extraction_confidence": 0.0
    }

    Each item in needs must contain:
    {
        "commodity": "string",
        "quantity": null,
        "unit": null,
        "evidence": []
    }
    """

    user_prompt = f"""
    Report ID: {report.report_id}
    Citizen message: {report.raw_text}
    Location text: {report.raw_location_text}
    Provided coordinates: {report.provided_location}

    Extract the emergency information.
    """

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    ai_content = result["choices"][0]["message"]["content"]
    extracted_data = json.loads(ai_content)

    extracted_data["report_id"] = report.report_id

    # Only use coordinates supplied by the citizen.
    extracted_data["coordinates"] = (
        report.provided_location.model_dump()
        if report.provided_location
        else None
    )

    # Verification is never decided by the LLM.
    extracted_data["verification_status"] = VerificationStatus.PENDING

    return ExtractedEmergencyReport.model_validate(extracted_data)
def validate_emergency_report(
    report: ExtractedEmergencyReport,
) -> ReportValidationResult:

    issues = []
    clarification_fields = list(report.missing_information)

    # Check incident type
    if not report.incident_type:
        issues.append("Incident type is missing.")
        clarification_fields.append("incident_type")

    # Check location
    if not report.location_description and not report.coordinates:
        issues.append("Emergency location is missing.")
        clarification_fields.append("location")

    # Check whether any emergency needs were identified
    if not report.needs:
        issues.append("No emergency needs were identified.")
        clarification_fields.append("needs")

    # Check whether quantities are specified
    for need in report.needs:
        if need.quantity is None:
            clarification_fields.append(
                f"quantity_for_{need.commodity}"
            )

    # Remove duplicate clarification fields
    clarification_fields = list(dict.fromkeys(clarification_fields))

    return ReportValidationResult(
        report_id=report.report_id,
        structurally_valid=len(issues) == 0,
        validation_issues=issues,
        clarification_fields=clarification_fields,
    )