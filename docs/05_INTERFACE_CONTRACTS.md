# 05 — Interface Contracts (v1; freeze before parallel coding)

## Rules
- Python 3.11+, Pydantic v2, type hints on all public functions.
- Async for network/database-bound service functions.
- All datetimes timezone-aware UTC internally; display local time in UI.
- Internal points use `LatLon(latitude=..., longitude=...)`.
- GeoJSON positions use `[longitude, latitude]`; do not pass raw coordinate arrays except in GeoJSON.
- Distance is metres; duration is seconds; precipitation is millimetres; ETA drift is minutes.
- Expected provider failures raise `ReliefRouteError`; do not return `None` as a generic error.
- `None` is allowed only when absence is a valid result, e.g. no known latest driver location.
- Never expose secrets to logs or API responses.

## Canonical public signatures
These signatures are declared as Protocols in `shared/contracts.py`:
```python
async def get_forecast(location: LatLon, *, horizon_hours: int = 3) -> list[WeatherObservation]: ...
async def assess(observations: list[WeatherObservation]) -> HazardAssessment: ...
async def list_available(commodity: str, *, min_quantity: float = 0) -> list[tuple[Supplier, InventoryItem]]: ...
async def register_supplier(supplier: Supplier) -> Supplier: ...
async def upsert_inventory(item: InventoryItem) -> InventoryItem: ...
async def calculate_safe_route(request: RouteRequest) -> RouteResult: ...
async def record_location(location: DriverLocation) -> DriverLocation: ...
async def latest_location(driver_id: str) -> DriverLocation | None: ...
async def create_plan(*, supplier: Supplier, inventory: InventoryItem, origin: LatLon, destination: LatLon, hazard: HazardAssessment) -> DeliveryPlan: ...
async def decide(request: ApprovalRequest) -> DeliveryPlan: ...
async def dispatch(request: DispatchRequest) -> DispatchResult: ...
async def record_acknowledgement(ack: DriverAcknowledgement) -> bool: ...
async def append(event: AuditEvent) -> None: ...
```

## Models
The actual Pydantic fields are authoritative in `shared/models.py`. Do not create parallel dataclasses/dicts for these entities.
- `LatLon`: latitude and longitude, range-validated.
- `SourceRef`: provider, URL if available, retrieved/observed times, stale flag, notes.
- `WeatherObservation`: location, forecast window, precipitation in mm, source.
- `HazardAssessment`: assessment ID, risk level, polygons, sources, rationale, limitations.
- `Supplier`: registered supplier and contact channel/handle.
- `InventoryItem`: supplier-reported commodity, quantity, unit, update/expiry times.
- `DriverLocation`: driver ID, location, observed time, source, optional accuracy and consent flag.
- `RouteRequest`: origin, destination, avoid polygons, profile, departure time.
- `RouteResult`: provider, optional GeoJSON geometry, distance metres, duration seconds, whether polygon avoidance was requested/confirmed, risk level, warnings, source.
- `DeliveryPlan`: supplier, requested goods, endpoints, route, hazard assessment ID, status, approval flag, idempotency key, rationale and sources.
- `ApprovalRequest`: plan ID, decision, approver ID, optional comment, timestamp.
- `DispatchRequest`: plan ID, driver ID, optional Telegram chat ID, message, idempotency key.
- `DispatchResult`: dispatch ID, plan ID, provider message ID, SENT/FAILED status and optional error.
- `DriverAcknowledgement`: plan ID, driver ID, acknowledged flag, timestamp and message.
- `AuditEvent`: actor, action, entity, outcome, details and source references.

## Idempotency
- Every plan has a stable unique `idempotency_key`; repeated requests with the same key return the existing plan.
- Every dispatch request has a unique key and is reserved atomically before sending. A confirmed retry returns the saved result; an in-progress or unresolved request is never sent again automatically.
- Definite Telegram rejection records `FAILED` and releases the plan to `APPROVED`, allowing an operator retry with a new key. A timeout or malformed response leaves the attempt unresolved; reconcile delivery with Telegram before any manual recovery.
- Approval decisions must record approver identity and time.
- A Telegram callback/update ID should be stored to prevent duplicate processing.
- Driver acknowledgement is accepted only for a confirmed dispatch to that driver. Identical acknowledgement retries do not duplicate audit events; `IN_TRANSIT` remains `IN_TRANSIT`.

## Error handling
Use `shared.enums.ErrorCode` and `shared.errors.ReliefRouteError`.
- Retryable: network timeout, temporary provider outage, rate limit (respect Retry-After).
- Not normally retryable: invalid input, provider authentication failure, invalid upstream schema.
- Bounded retry: max 2 attempts beyond first attempt for EOD; exponential backoff with jitter if time allows.
- After retry exhaustion, surface a failed/degraded status and preserve the last known result with its timestamp. Never claim the latest data is current if it is stale.
