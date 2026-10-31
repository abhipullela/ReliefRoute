# 06 — Data Models and Database

## Database
`db/schema.sql` is the v1 logical schema. For today's prototype, PostgreSQL is preferred; SQLite can be used only for local development if all SQL differences are documented. Do not change column semantics casually.

## Tables
- `suppliers`: registered supplier identity, coordinates, contact, active/verified state.
- `inventory`: supplier-reported commodity, quantity, unit, update/expiry times.
- `driver_locations`: timestamped driver coordinates and source/consent.
- `plans`: status, unique idempotency key, canonical plan payload.
- `dispatches`: dispatch attempts, unique idempotency key, provider message ID.
- `audit_events`: append-only record of important actions and outcomes.

## Data freshness
- Weather: record retrieval time and forecast window; warn if older than `WEATHER_MAX_AGE_MINUTES`.
- Driver GPS: reject or mark stale if older than `DRIVER_LOCATION_MAX_AGE_MINUTES`.
- Inventory: use supplier-reported `updated_at`; do not treat expired or stale inventory as available without an explicit warning/confirmation.
- Hazard layer: store source and observation/acquisition timestamp where provided.
- Routing: store route provider and retrieval time.

## Supplier inventory semantics
Inventory is a supplier's declared stock, not a market estimate. A mandi arrival/price feed may inform regional market context but cannot prove that a specific supplier has a quantity available.

## Coordinates and geometry
- Internal location: named latitude/longitude fields.
- GeoJSON: `[longitude, latitude]`.
- Validate polygon rings are closed and geometries valid before routing.
- If a polygon is malformed, fail assessment or drop only with a visible warning and logged reason; never silently send invalid geometry.

## Privacy
Collect only the driver location needed for the delivery, disclose it to participants, restrict access, and retain only what the demo requires. Do not commit real phone numbers, bot tokens, API keys, or personal location traces to Git.
