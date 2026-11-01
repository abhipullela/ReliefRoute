# 02 — Architecture and Data Flow

## Components
- `shared/`: canonical Pydantic models, enums, error contract, and Protocol signatures.
- `services/`: external provider adapters and domain services.
- `agent/`: state machine and planning orchestration; never duplicate provider clients.
- `api/`: FastAPI boundary for dashboard and integrations.
- `bot/`: Telegram input/output for drivers and suppliers.
- `web/`: operator UI; communicates only through HTTP API.
- `db/`: PostgreSQL schema/migrations.
- `tests/`: unit, contract, integration and acceptance tests.

## Dependency direction
`web/bot -> api -> agent/services -> database/provider APIs`
Shared contracts may be imported by all Python components. `agent/` must not import provider SDK code directly; it calls service interfaces. `web/` must not access PostgreSQL directly.

## Main flow
1. Weather service retrieves forecast and records source/retrieval time.
2. Hazard service creates an assessment with evidence, risk, limitations and polygons where justified.
3. Supplier service returns only active supplier-reported inventory that is fresh and sufficient.
4. Routing service computes a candidate route with avoid polygons where provider supports it; returns warnings and provenance.
5. Planning service creates a `DRAFT` plan and deterministic idempotency key.
6. Guardrail checks validate data freshness, supplier stock, route response and approval policy.
7. Plan becomes `NEEDS_APPROVAL`; operator approves or rejects.
8. Dispatch service sends only an approved plan and stores idempotency key.
9. Driver acknowledgement is a distinct event from message sent.
10. Verify stage checks freshness, acknowledgement and ETA drift; replan within bounded retry count.

Citizen reports enter through the API, are stored in `citizen_reports`, and are
processed by `agent/citizen_reports.py`. The agent invokes the OpenAI-compatible
GenAI adapter in `services/genai.py` only after per-report consent. The
classification remains advisory and requires a human to review it.

## No false guarantees
- Weather polygon = modeled/forecast risk area, not verified road closure.
- Route avoids polygon = provider-calculated geometry, not proof of safety.
- Telegram send success = platform accepted a message, not proof driver complied.
- Empty supplier result = no matching fresh stock found in the database, not proof no stock exists anywhere.

## Suggested technology
Python 3.11+, FastAPI, Pydantic v2, PostgreSQL, LangGraph (optional for first vertical slice), Open-Meteo, OpenRouteService if configured, OpenStreetMap/Overpass if needed, Telegram Bot API, Leaflet/MapLibre frontend.
