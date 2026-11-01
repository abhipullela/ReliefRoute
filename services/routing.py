"""Live road routing through OSRM, with explicit hazard-polygon checks."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from shapely.geometry import LineString, shape
from shapely.errors import ShapelyError

from shared.enums import ErrorCode, RiskLevel
from shared.errors import ReliefRouteError
from shared.models import RouteRequest, RouteResult, SourceRef

from datetime import datetime, timezone

OSRM_BASE_URL = "https://router.project-osrm.org"
OSRM_PROVIDER = "OSRM public routing service"


class OSRMRoutingService:
    """Calculate real road routes and check them against supplied hazard polygons.

    Important:
    - OSRM provides routes, not flood-safety guarantees.
    - Alternative routes are limited to those returned by OSRM.
    - If every returned route intersects a hazard polygon, the service
      returns the best available route with an explicit warning.
    """

    def __init__(
        self,
        *,
        base_url: str = OSRM_BASE_URL,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def calculate_safe_route(
        self,
        request: RouteRequest,
    ) -> RouteResult:
        """Request real routes and select one that avoids supplied polygons if possible."""

        if request.profile != "driving-car":
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "OSRM implementation currently supports only the driving-car profile.",
                provider=OSRM_PROVIDER,
            )

        # OSRM expects longitude,latitude—not latitude,longitude.
        coordinates = (
            f"{request.origin.longitude},{request.origin.latitude};"
            f"{request.destination.longitude},{request.destination.latitude}"
        )

        url = f"{self.base_url}/route/v1/driving/{coordinates}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "true",
            "steps": "false",
        }

        payload = await self._fetch_routes(url, params)
        routes = payload.get("routes")

        if not isinstance(routes, list) or not routes:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "OSRM returned no routes.",
                provider=OSRM_PROVIDER,
            )

        # Prepare valid hazard geometries. An invalid polygon is a data-quality
        # problem: do not silently treat it as an area that can be avoided.
        hazard_shapes = []

        try:
            for polygon in request.avoid_polygons:
                geometry = shape(polygon.model_dump())
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError("A supplied hazard polygon is empty or invalid.")
                hazard_shapes.append(geometry)
        except (ValueError, ShapelyError, TypeError) as exc:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                f"Invalid hazard polygon: {exc}",
                provider=OSRM_PROVIDER,
            ) from exc

        candidates: list[dict[str, Any]] = []

        for route in routes:
            try:
                geometry_data = route["geometry"]
                line = shape(geometry_data)

                if line.geom_type != "LineString" or line.is_empty:
                    continue

                distance_m = float(route["distance"])
                duration_s = float(route["duration"])

                if distance_m < 0 or duration_s < 0:
                    continue

                intersects_hazard = any(
                    line.intersects(hazard) for hazard in hazard_shapes
                )

                candidates.append(
                    {
                        "route": route,
                        "line": line,
                        "intersects_hazard": intersects_hazard,
                        "distance_m": distance_m,
                        "duration_s": duration_s,
                    }
                )
            except (KeyError, TypeError, ValueError, ShapelyError):
                # Skip malformed alternatives; never invent replacement geometry.
                continue

        if not candidates:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                "OSRM returned no usable route geometries.",
                provider=OSRM_PROVIDER,
            )

        # Prefer routes that avoid all supplied polygons. Among those, prefer
        # shorter duration. If none avoids the polygons, return the fastest
        # candidate but explicitly mark the avoidance failure.
        safe_candidates = [
            candidate
            for candidate in candidates
            if not candidate["intersects_hazard"]
        ]

        selected = min(
            safe_candidates or candidates,
            key=lambda candidate: candidate["duration_s"],
        )

        avoids_requested_polygons = not selected["intersects_hazard"]
        warnings: list[str] = [
            "Route geometry is from OSRM; this is not a guarantee of road "
            "passability or real-time road conditions."
        ]

        if hazard_shapes and not avoids_requested_polygons:
            warnings.append(
                "Every usable route returned by OSRM intersects at least one "
                "supplied hazard polygon. This route has NOT been verified "
                "to avoid those hazards. Human review is required."
            )
        elif hazard_shapes:
            warnings.append(
                "The selected route does not geometrically intersect the "
                "supplied hazard polygons. This does not establish that the "
                "roads are safe or passable."
            )

        return RouteResult(
            provider=OSRM_PROVIDER,
            geometry=selected["route"]["geometry"],
            distance_m=selected["distance_m"],
            duration_s=selected["duration_s"],
            avoids_requested_polygons=avoids_requested_polygons,
            risk_level=RiskLevel.UNKNOWN,
            warnings=warnings,
            source=SourceRef(
                provider=OSRM_PROVIDER,
                url=url,
                retrieved_at=datetime.now(timezone.utc)
                if hasattr(httpx, "Timestamp")
                else __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                notes=(
                    "Live road route from OSRM. Hazard intersection is a "
                    "geometric check only; flood depth, closures and road "
                    "passability are not verified."
                ),
            ),
        )

    async def _fetch_routes(
        self,
        url: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Fetch OSRM data with bounded retries and explicit upstream errors."""

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds
                ) as client:
                    response = await client.get(url, params=params)

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue

                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        f"OSRM returned HTTP {response.status_code}.",
                        retryable=True,
                        provider=OSRM_PROVIDER,
                    )

                if response.status_code in (401, 403):
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_AUTH_FAILED,
                        f"OSRM returned HTTP {response.status_code}.",
                        provider=OSRM_PROVIDER,
                    )

                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "OSRM returned invalid JSON.",
                        provider=OSRM_PROVIDER,
                    ) from exc

                if not isinstance(payload, dict):
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "OSRM response must be a JSON object.",
                        provider=OSRM_PROVIDER,
                    )

                if payload.get("code") != "Ok":
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        f"OSRM routing failed: {payload.get('message', payload.get('code'))}",
                        provider=OSRM_PROVIDER,
                    )

                return payload

            except ReliefRouteError:
                raise
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue

                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_TIMEOUT
                    if isinstance(exc, httpx.TimeoutException)
                    else ErrorCode.UPSTREAM_UNAVAILABLE,
                    f"Unable to retrieve a route from OSRM: {exc}",
                    retryable=True,
                    provider=OSRM_PROVIDER,
                ) from exc
            except httpx.HTTPStatusError as exc:
                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    f"OSRM returned HTTP {exc.response.status_code}.",
                    provider=OSRM_PROVIDER,
                ) from exc

        raise ReliefRouteError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "OSRM request failed after retries.",
            retryable=True,
            provider=OSRM_PROVIDER,
        )