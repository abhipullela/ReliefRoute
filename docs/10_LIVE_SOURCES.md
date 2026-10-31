# 10 — Live Data Sources and Verification

Record provider status in a team table before coding. “Free” does not mean unlimited or guaranteed available.

| Source | Use | Verification needed | Fallback behavior |
|---|---|---|---|
| Open-Meteo Forecast API (`https://open-meteo.com/`) | Precipitation forecast for pilot coordinates | Make a real HTTP request; record variables, timezone, response time | Show degraded/no current assessment; never fabricate |
| OpenRouteService (`https://openrouteservice.org/`) | Candidate route and avoid polygons, subject to endpoint/plan limits | Verify key, route profile, request schema, avoid-polygon support and response geometry | Show routing unavailable; no dispatch |
| OpenStreetMap / Overpass (`https://overpass-api.de/`) | Road/POI context where needed | Check rate limits and query cost; don't treat OSM as live closure status | Use routing provider or explicit unavailable |
| Agmarknet / data.gov.in (`https://data.gov.in/`) | Market arrivals/prices | Verify API key, dataset, filters, units and update cadence | Mark optional; never use as supplier inventory |
| Copernicus EMS (`https://emergency.copernicus.eu/`) / ISRO Bhuvan (`https://bhuvan.nrsc.gov.in/`) | Official/satellite flood context if accessible | Verify downloadable layer, license, spatial extent and observation date | Weather-derived risk only, clearly labeled |
| Telegram Bot API (`https://core.telegram.org/bots/api`) | Supplier registration, driver GPS and dispatch | Verify bot token and real phone interaction; configure webhook/polling | UI/manual operator input only if honestly labeled |

## Required provider smoke-test record
For each integration, add to the PR:
- Exact endpoint/dataset and documentation link.
- UTC timestamp of successful test.
- Sanitized example response shape (no secrets/PII).
- Rate limits/auth requirements.
- Timeout and failure behavior.
- Whether the integration is live, optional, or unavailable.

Do not state an API works until a real request has succeeded. If a source is not verified, label it “not integrated” in the demo.
