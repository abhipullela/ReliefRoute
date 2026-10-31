# ReliefRoute

**When the roads flood, relief finds a way.**

ReliefRoute is a hazard-aware logistics prototype for extreme-rain events in Karnataka. It connects live weather information, registered supplier inventory, geospatial routing, driver-reported locations, and an approval-gated dispatch workflow.

> Safety boundary: a route that avoids mapped hazard polygons is not guaranteed safe or passable. Display risk and source freshness explicitly. Never fabricate inventory, GPS, road closures, or delivery outcomes.

## Today's EOD objective

Ship one reliable vertical slice, not every planned integration:
1. Fetch real Open-Meteo forecast data for the configured pilot area.
2. Accept a real supplier registration and inventory update.
3. Accept real driver GPS via Telegram or the web location form.
4. Generate a hazard-aware candidate route if the routing API is configured; otherwise show a clear `ROUTING_UNAVAILABLE` state.
5. Show a plan in the UI/API, require human approval, send a dispatch message, and record acknowledgement.
6. Log every state transition and external action.

Agmarknet and satellite flood layers are stretch goals unless already verified working. Agmarknet arrivals are not supplier inventory.

## Quick start

1. Copy `.env.example` to `.env` and fill only keys you have verified.
2. Create a virtual environment and install the project dependencies.
3. Read `docs/00_START_HERE.md`, then `docs/05_INTERFACE_CONTRACTS.md`.
4. Run `pytest`.
5. Follow `docs/04_GIT_AND_TEAM_WORKFLOW.md`.

The documents in `docs/` are the implementation source of truth. If code and docs disagree, open a contract-change PR; do not silently invent a new interface.

## Live Weather Integration

ReliefRoute integrates with the Open-Meteo Forecast API to retrieve real hourly precipitation forecasts for specified geographic coordinates.

### Implementation

The weather integration is implemented in `services/weather.py`.

Responsibilities include:

* Fetching live precipitation forecasts from the external API.
* Validating the upstream response before processing it.
* Converting forecast measurements into the shared `WeatherObservation` model.
* Recording the provider and retrieval timestamp.
* Handling timeouts, rate limits, network failures, and invalid responses.
* Preserving missing measurements rather than treating them as zero.

Weather observations represent forecasts, not verified road conditions. Rainfall measurements alone do not establish that a road is flooded or impassable.

### Live Verification

The `check_weather_live.py` script verifies connectivity to the live weather provider and displays the returned observations.

Run it from the repository root:

```powershell
python check_weather_live.py
```

The script requests a three-hour precipitation forecast for the specified coordinates and displays the provider, number of observations, forecast timestamps, and precipitation values.

The results are retrieved at runtime. They are not stored in a hardcoded response or replaced with fabricated measurements when the provider is unavailable.

### Dependencies

The implementation requires the project's configured dependencies, including `httpx` for asynchronous HTTP requests.

Activate the project's virtual environment before running the check.

### Verification Scope

A successful run demonstrates that:

1. The application can reach the external weather provider.
2. The service can retrieve and process a real forecast response.
3. The resulting observations use the project's shared data models.

This check verifies the weather integration only. It does not establish that hazard assessment, routing, dispatch, or the complete delivery workflow is operational.
