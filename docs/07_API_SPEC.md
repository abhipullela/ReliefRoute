# 07 — HTTP API Specification (v1)

Prefix: `/api/v1`. JSON request/response bodies use the canonical Pydantic models where applicable. FastAPI-generated OpenAPI docs are available at `/docs`.

## Endpoints to implement
- `GET /health` — process health; no provider dependencies.
- `GET /api/v1/weather?latitude={lat}&longitude={lon}&horizon_hours=3` — weather observations plus source metadata.
- `POST /api/v1/suppliers` — register supplier (`Supplier`).
- `POST /api/v1/inventory` — upsert supplier-reported inventory (`InventoryItem`).
- `POST /api/v1/driver-locations` — record driver GPS (`DriverLocation`).
- `GET /api/v1/drivers/{driver_id}/location` — latest location; 404 if none.
- `POST /api/v1/plans` — create candidate plan from validated supplier/inventory, origin/destination and hazard assessment; response `DeliveryPlan`.
- `GET /api/v1/plans/{plan_id}` — fetch current plan.
- `POST /api/v1/plans/{plan_id}/approval` — `ApprovalRequest`; only authorized operators can decide.
- `POST /api/v1/plans/{plan_id}/dispatch` — `DispatchRequest`; only approved plans can dispatch.
- `POST /api/v1/plans/{plan_id}/acknowledgements` — `DriverAcknowledgement`.
- `GET /api/v1/audit-events?entity_id={id}` — events for an entity/plan.

## HTTP status semantics
- `200`: successful read/update.
- `201`: new entity created.
- `400`: invalid business transition (e.g. dispatch before approval).
- `401/403`: missing/insufficient authentication/authorization in deployed mode.
- `404`: entity not found.
- `409`: idempotency conflict or invalid state transition.
- `422`: Pydantic/input validation failure.
- `429`: rate limited.
- `502`: upstream provider returned invalid/unusable response.
- `503`: provider unavailable after bounded retries.
- `504`: upstream timeout.
- `500`: unexpected internal error; return correlation ID, not secrets.

## Required response behavior
Every response that depends on external data should expose source, retrieval/observation time, and stale/warning information. Error responses should have stable `code`, safe `message`, `retryable`, and `correlation_id` fields. Do not return stack traces or credentials.
