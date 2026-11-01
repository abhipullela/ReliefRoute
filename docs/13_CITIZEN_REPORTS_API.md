# Citizen Reports API and Frontend Contract

The existing FastAPI application exposes citizen-report routes at the root path
(there is no `/api/v1` prefix in the current implementation). Requests and
responses use JSON.

## Submit a report

`POST /citizen-reports` returns `201 Created` with a `CitizenReport`.

Request:

```json
{
  "report_text": "Flood water is covering the road near the school.",
  "location": {
    "latitude": 12.711,
    "longitude": 77.695
  },
  "observed_at": "2026-11-01T10:00:00Z",
  "idempotency_key": "client-generated-unique-key",
  "ai_processing_consent": true
}
```

`report_text` is required (10–5000 characters). `location` and `observed_at`
are optional; if omitted, the report has no location and `observed_at` is set
when the report is first stored. `idempotency_key` is required and should be
stable across retries of the same submission. `ai_processing_consent` defaults
to `false`; without explicit consent, the report is stored but its text is not
sent to the GenAI provider.

Response:

```json
{
  "report_id": "server-generated-id",
  "report_text": "Flood water is covering the road near the school.",
  "location": {
    "latitude": 12.711,
    "longitude": 77.695
  },
  "observed_at": "2026-11-01T10:00:00Z",
  "created_at": "2026-11-01T10:01:00Z",
  "updated_at": "2026-11-01T10:01:02Z",
  "idempotency_key": "client-generated-unique-key",
  "ai_processing_consent": true,
  "triage_status": "COMPLETE",
  "triage": {
    "category": "FLOODING",
    "severity": "HIGH",
    "summary": "A resident reports floodwater covering a road.",
    "confidence": 0.87,
    "needs_human_review": true,
    "generated_at": "2026-11-01T10:01:02Z",
    "provider": "openai_compatible",
    "model": "configured-model-name"
  },
  "triage_error": null
}
```

The sample values above describe the response shape only; the API does not
hardcode report content or provider responses. Real IDs, timestamps, summaries,
and classifications come from storage and configured provider results.

`triage_status` values:

| Value | Meaning |
|---|---|
| `PENDING` | Stored and waiting for AI triage. |
| `PROCESSING` | A worker holds the triage claim. |
| `COMPLETE` | A validated AI advisory result is available. |
| `NOT_REQUESTED` | AI consent was not given; no AI request was made. |
| `UNAVAILABLE` | The report is stored, but the GenAI provider is not configured or available. |
| `FAILED` | Triage failed due to a non-transient or invalid provider result. |

If GenAI is unavailable, submission still returns the stored report with
`triage_status: "UNAVAILABLE"` and no fabricated triage. A repeated submission
with the same key and same fields returns the existing report; reusing the key
with different fields returns `409 Conflict`. If `observed_at` was omitted, a
retry may omit it too without changing the report's stored observation time.

## Read reports

- `GET /citizen-reports?limit=50&offset=0&triage_status=COMPLETE`
  - `limit`: optional, 1–100, default 50.
  - `offset`: optional, non-negative, default 0.
  - `triage_status`: optional enum filter.
  - Returns an array sorted newest first.
- `GET /citizen-reports/{report_id}`
  - Returns one report or `404 Not Found`.

## Retry triage

`POST /citizen-reports/{report_id}/triage` retries a report only when its
submission included AI-processing consent. It returns the existing report if a
triage is already complete or currently claimed. Database claim tokens and a
five-minute stale-claim lease prevent parallel workers from overwriting one
another's result.

## GenAI output and safety

Configure `LLM_API_KEY`, `LLM_MODEL`, and optionally `LLM_BASE_URL` (defaults to
`https://api.openai.com/v1`). The provider uses the OpenAI-compatible
`POST {LLM_BASE_URL}/chat/completions` endpoint with JSON output mode. Only
report text is sent; location is deliberately excluded. Provider credentials
are not returned or logged by the implementation.

Supported categories: `FLOODING`, `ROAD_BLOCKAGE`, `INFRASTRUCTURE_DAMAGE`,
`MEDICAL_EMERGENCY`, `SUPPLY_NEED`, `OTHER`.

Supported severities: `INFORMATIONAL`, `MODERATE`, `HIGH`, `CRITICAL`.

The AI classification is unverified and is always marked
`needs_human_review: true`. It must not be used by the frontend to claim that
an incident is verified, to make emergency decisions, or to approve or dispatch
relief. Show both the original citizen report and the AI advisory distinctly.

## Deployment limitation

The application currently has no API authentication, authorization, retention
policy, or rate limiting. Citizen reports can contain sensitive personal
information. Keep the service private until those controls, access scoping, and
an appropriate privacy notice are in place.
