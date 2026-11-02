"""Agmarknet market-arrival adapter.

This adapter reads market arrivals from the public Agmarknet 2.0 API.
It deliberately does NOT turn arrivals into supplier inventory: arrivals are
market-level supply signals, not stock confirmed as available for dispatch.

The upstream API is a public website backend, not a versioned public API
contract. Treat response-shape changes as INVALID_UPSTREAM_RESPONSE.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError

AGMARKNET_URL = (
    "https://api.agmarknet.gov.in/v1/"
    "price-trend/wholesale-arrivals-monthly"
)

AGMARKNET_BASE_URL = "https://api.agmarknet.gov.in/v1"
AGMARKNET_PROVIDER = "Agmarknet 2.0"
ARRIVALS_ENDPOINT = "/prices-and-arrivals/date-wise/specific-commodity"

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://agmarknet.gov.in",
    "Referer": "https://agmarknet.gov.in/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}

# The upstream has used several field spellings across report endpoints.
_DATE_KEYS = ("arrival_date", "date", "reported_date", "report_date", "arrivalDate")
_MARKET_KEYS = ("market", "market_name", "marketName", "apmc", "mandi")
_DISTRICT_KEYS = ("district", "district_name", "districtName")
_STATE_KEYS = ("state", "state_name", "stateName")
_COMMODITY_KEYS = ("commodity", "commodity_name", "commodityName", "commodity_name_en")
_VARIETY_KEYS = ("variety", "variety_name", "varietyName")
_QUANTITY_KEYS = (
    "arrivals", "arrival", "arrival_qty", "arrival_quantity", "arrivalQuantity",
    "quantity_arrived", "quantityArrived", "arrival_qty_qtl", "arrivals_quantity",
)
_UNIT_KEYS = ("arrival_unit", "arrivalUnit", "unit", "unit_name", "quantity_unit")


# @dataclass(frozen=True, slots=True)
# class MandiArrivalObservation:
#     """Normalized market-arrival record, with provider provenance.

#     `quantity` is intentionally paired with the upstream unit; the adapter
#     does not assume that all commodities are reported in the same unit.
#     """

#     commodity: str
#     market: str
#     arrival_date: date
#     quantity: float
#     unit: str
#     state: str | None
#     district: str | None
#     variety: str | None
#     source_provider: str
#     source_url: str
#     retrieved_at: datetime
#     observed_at: datetime | None

# from dataclasses import dataclass
# from datetime import date, datetime


# @dataclass(frozen=True)
# class MandiArrivalObservation:
#     commodity: str
#     market: str
#     arrival_date: date

#     # Optional because the upstream provider may omit these fields.
#     quantity: float | None
#     unit: str | None

#     state: str | None
#     district: str | None
#     variety: str | None

#     source_provider: str
#     source_url: str
#     retrieved_at: datetime
#     observed_at: datetime | None



@dataclass(frozen=True)
class MandiArrivalObservation:
    commodity: str
    market: str

    # Monthly aggregate, for example "2026-10".
    arrival_period: str

    # Missing quantity is valid; it does not mean zero.
    quantity: float | None = None
    unit: str | None = None

    state: str | None = None
    district: str | None = None
    variety: str | None = None

    source_provider: str = "Agmarknet 2.0"
    source_url: str = ""
    retrieved_at: datetime | None = None



def parse_monthly_arrivals(
    payload: dict,
    year: int,
    month: int,
) -> list[MandiArrivalObservation]:
    month_name = datetime(year, month, 1).strftime("%B").lower()
    quantity_key = f"arrivals_{month_name}_{year}"

    if payload.get("success") is not True:
        raise ValueError("Agmarknet reported an unsuccessful response")

    rows = payload.get("rows")

    if not isinstance(rows, list):
        raise ValueError("Agmarknet response does not contain valid rows")

    observations = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid market row")

        market = row.get("market")

        # Do not treat the aggregate total as an individual market.
        if not isinstance(market, str) or not market.strip():
            continue

        if market.strip().casefold() == "total":
            continue

        raw_quantity = row.get(quantity_key)

        if raw_quantity is None:
            quantity = None
        elif isinstance(raw_quantity, bool):
            raise ValueError("Boolean is not a valid arrival quantity")
        else:
            try:
                quantity = float(raw_quantity)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid quantity for market {market!r}"
                ) from exc

            if quantity < 0:
                raise ValueError(
                    f"Negative quantity for market {market!r}"
                )

        observations.append(
            MandiArrivalObservation(
                commodity=payload.get("commodity", "Unknown"),
                market=market.strip(),
                arrival_period=f"{year:04d}-{month:02d}",
                quantity=quantity,
                unit="metric tonnes" if quantity is not None else None,
                state=None,
                district=None,
                source_provider="Agmarknet 2.0",
                source_url=AGMARKNET_URL,
                retrieved_at=datetime.now().astimezone(),
            )
        )

    return observations

def _first(record: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    """Case-insensitive field lookup, preserving the original value."""
    lowered = {str(key).casefold(): value for key, value in record.items()}
    for name in names:
        value = lowered.get(name.casefold())
        if value is not None and value != "":
            return value
    return None


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("arrival date is missing or not a string")
    raw = value.strip()
    # Common Agmarknet date representations.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d",
                "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"unparseable arrival date: {raw!r}") from exc


def _parse_quantity(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError("arrival quantity is missing or invalid")
    if isinstance(value, (int, float)):
        quantity = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned in {"", "-", "--", "NA", "N/A", "null"}:
            raise ValueError("arrival quantity is missing or invalid")
        quantity = float(cleaned)
    else:
        raise ValueError("arrival quantity has an unsupported type")
    if quantity < 0:
        raise ValueError("arrival quantity cannot be negative")
    return quantity


def _extract_records(payload: Any) -> list[Mapping[str, Any]]:
    """Extract record-shaped objects from known/common JSON envelope shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if not isinstance(payload, Mapping):
        raise ValueError("expected a JSON object or array")

    for key in ("data", "records", "result", "results", "items", "response"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            nested = _extract_records(value)
            if nested:
                return nested

    # A single record is accepted, but an arbitrary metadata object is not.
    if _first(payload, _COMMODITY_KEYS) is not None and _first(payload, _QUANTITY_KEYS) is not None:
        return [payload]

    # Explicit no-data responses are treated as an empty result, not a fabricated record.
    success = payload.get("success")
    message = str(payload.get("message", "")).casefold()
    if success is False and any(term in message for term in ("no data", "no record", "not found")):
        return []
    if payload.get("data") is None and any(term in message for term in ("no data", "no record", "not found")):
        return []
    raise ValueError("response did not contain a recognized arrivals record list")


class AgmarknetMandiService:
    """Fetch and normalize monthly arrivals for one state and commodity.

    Parameters use Agmarknet's internal numeric IDs, not display names:
    `state_id` and `commodity_id`. Obtain these from the site's filter data.
    """

    def __init__(
        self,
        *,
        base_url: str = AGMARKNET_BASE_URL,
        timeout_seconds: float = 12.0,
        max_attempts: int = 3,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    async def get_arrivals(
        self,
        *,
        year: int,
        month: int,
        state_id: int,
        commodity_id: int,
    ) -> list[MandiArrivalObservation]:
        """Return real reported arrivals for the requested state/commodity/month."""
        if not 2000 <= year <= 2100:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR, "year must be between 2000 and 2100",
                provider=AGMARKNET_PROVIDER,
            )
        if not 1 <= month <= 12:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR, "month must be between 1 and 12",
                provider=AGMARKNET_PROVIDER,
            )
        if state_id <= 0 or commodity_id <= 0:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "state_id and commodity_id must be positive Agmarknet IDs",
                provider=AGMARKNET_PROVIDER,
            )

        url = f"{self.base_url}{ARRIVALS_ENDPOINT}"
        params = {
            "year": year,
            "month": month,
            "stateId": state_id,
            "commodityId": commodity_id,
        }
        payload = await self._fetch(url, params)
        retrieved_at = datetime.now(UTC)

        try:
            records = _extract_records(payload)
            observations: list[MandiArrivalObservation] = []
            for record in records:
                quantity_value = _first(record, _QUANTITY_KEYS)
                if quantity_value is None:
                    # Some report envelopes include metadata/summary rows.
                    continue
                commodity_value = _first(record, _COMMODITY_KEYS)
                market_value = _first(record, _MARKET_KEYS)
                date_value = _first(record, _DATE_KEYS)
                unit_value = _first(record, _UNIT_KEYS)

                if not commodity_value or not market_value or date_value is None:
                    raise ValueError("arrival record is missing commodity, market, or date")
                if unit_value is None:
                    # Do not invent a unit when the source omits it.
                    raise ValueError("arrival record is missing its quantity unit")

                parsed_date = _parse_date(date_value)
                if parsed_date.year != year or parsed_date.month != month:
                    # Ignore records outside the requested month, rather than relabel them.
                    continue

                observations.append(
                    MandiArrivalObservation(
                        commodity=str(commodity_value).strip(),
                        market=str(market_value).strip(),
                        arrival_date=parsed_date,
                        quantity=_parse_quantity(quantity_value),
                        unit=str(unit_value).strip(),
                        state=_optional_text(_first(record, _STATE_KEYS)),
                        district=_optional_text(_first(record, _DISTRICT_KEYS)),
                        variety=_optional_text(_first(record, _VARIETY_KEYS)),
                        source_provider=AGMARKNET_PROVIDER,
                        source_url=url,
                        retrieved_at=retrieved_at,
                        observed_at=datetime.combine(
                            parsed_date, datetime.min.time(), tzinfo=UTC
                        ),
                    )
                )
            return observations
        except (TypeError, ValueError, OverflowError) as exc:
            raise ReliefRouteError(
                ErrorCode.INVALID_UPSTREAM_RESPONSE,
                f"Agmarknet returned an invalid arrivals payload: {exc}",
                provider=AGMARKNET_PROVIDER,
            ) from exc

    async def _fetch(self, url: str, params: dict[str, int]) -> Any:
        """Fetch JSON with bounded retries and distinct provider errors."""
        for attempt in range(self.max_attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, headers=_HEADERS
                ) as client:
                    response = await client.get(url, params=params)

                if response.status_code == 429:
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
                        continue
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_RATE_LIMITED,
                        "Agmarknet rate limit exceeded",
                        retryable=True,
                        provider=AGMARKNET_PROVIDER,
                    )
                if response.status_code in (401, 403):
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_AUTH_FAILED,
                        "Agmarknet rejected the request; public endpoint access may have changed",
                        provider=AGMARKNET_PROVIDER,
                        details={"status_code": response.status_code},
                    )
                if response.status_code >= 500:
                    if attempt + 1 < self.max_attempts:
                        await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
                        continue
                    raise ReliefRouteError(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Agmarknet is temporarily unavailable",
                        retryable=True,
                        provider=AGMARKNET_PROVIDER,
                        details={"status_code": response.status_code},
                    )
                if response.status_code >= 400:
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "Agmarknet rejected the arrivals request",
                        provider=AGMARKNET_PROVIDER,
                        details={"status_code": response.status_code},
                    )
                try:
                    return response.json()
                except ValueError as exc:
                    raise ReliefRouteError(
                        ErrorCode.INVALID_UPSTREAM_RESPONSE,
                        "Agmarknet returned invalid JSON",
                        provider=AGMARKNET_PROVIDER,
                    ) from exc
            except ReliefRouteError:
                raise
            except httpx.TimeoutException as exc:
                if attempt + 1 < self.max_attempts:
                    await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
                    continue
                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    "Timed out while requesting Agmarknet arrivals",
                    retryable=True,
                    provider=AGMARKNET_PROVIDER,
                ) from exc
            except httpx.RequestError as exc:
                if attempt + 1 < self.max_attempts:
                    await asyncio.sleep(min(0.5 * (2**attempt), 2.0))
                    continue
                raise ReliefRouteError(
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Could not connect to Agmarknet",
                    retryable=True,
                    provider=AGMARKNET_PROVIDER,
                ) from exc

        raise ReliefRouteError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "Agmarknet request ended unexpectedly",
            retryable=True,
            provider=AGMARKNET_PROVIDER,
        )


def _optional_text(value: Any) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()
