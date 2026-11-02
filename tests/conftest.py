"""Test fixtures and mock services for ReliefRoute agent unit tests."""

from datetime import UTC, datetime

import pytest

from agent.services import AgentServices
from agent.state import IncidentInfo
from shared.enums import RiskLevel
from shared.models import (
    AuditEvent,
    DispatchResult,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteRequest,
    RouteResult,
    SourceRef,
    Supplier,
    WeatherObservation,
    utc_now,
)

# ---------------------------------------------------------------------------
# Shared sample fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_origin() -> LatLon:
    """Origin coordinate (e.g., supplier in Bengaluru)."""
    return LatLon(latitude=12.9716, longitude=77.5946)


@pytest.fixture
def sample_destination() -> LatLon:
    """Destination coordinate (e.g., pilot in Anekal)."""
    return LatLon(latitude=12.7110, longitude=77.6950)


@pytest.fixture
def sample_source_ref() -> SourceRef:
    """Standard source reference for Open-Meteo."""
    return SourceRef(
        provider="open-meteo",
        url="https://api.open-meteo.com",
        retrieved_at=datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC),
        observed_at=datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC),
        stale=False,
        notes="Forecast for Bengaluru-Anekal pilot",
    )


@pytest.fixture
def sample_weather_observations(
    sample_destination: LatLon,
    sample_source_ref: SourceRef,
) -> list[WeatherObservation]:
    """Sample weather observations."""
    return [
        WeatherObservation(
            location=sample_destination,
            forecast_start=datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC),
            forecast_end=datetime(2026, 10, 31, 15, 0, 0, tzinfo=UTC),
            precipitation_mm=42.5,
            source=sample_source_ref,
        )
    ]


@pytest.fixture
def sample_hazard_assessment(sample_source_ref: SourceRef) -> HazardAssessment:
    """Sample structured hazard assessment."""
    return HazardAssessment(
        assessment_id="hz_20261031_001",
        generated_at=utc_now(),
        risk_level=RiskLevel.MODERATE,
        polygons=[],
        sources=[sample_source_ref],
        rationale=["Precipitation forecast exceeds 40mm in Anekal district."],
        limitations=["Modeled risk based on Open-Meteo numerical forecast, not verified road closures."],
    )


@pytest.fixture
def sample_supplier(sample_origin: LatLon) -> Supplier:
    """Sample active supplier."""
    return Supplier(
        supplier_id="sup_bangalore_01",
        name="Bengaluru Dairy Cooperative",
        location=sample_origin,
        contact_channel="telegram",
        contact_handle="@blr_dairy_rep",
        verified_at=datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC),
        active=True,
    )


@pytest.fixture
def sample_inventory() -> InventoryItem:
    """Sample supplier-reported inventory."""
    return InventoryItem(
        supplier_id="sup_bangalore_01",
        commodity="drinking_water",
        quantity=500.0,
        unit="box",
        updated_at=datetime(2026, 10, 31, 10, 0, 0, tzinfo=UTC),
        expires_at=datetime(2026, 11, 15, 0, 0, 0, tzinfo=UTC),
        source="supplier_reported",
    )


@pytest.fixture
def sample_route_result(sample_source_ref: SourceRef) -> RouteResult:
    """Sample candidate route result."""
    return RouteResult(
        provider="openrouteservice",
        geometry={"type": "LineString", "coordinates": [[77.5946, 12.9716], [77.6950, 12.7110]]},
        distance_m=35400.0,
        duration_s=2850.0,
        avoids_requested_polygons=True,
        risk_level=RiskLevel.MODERATE,
        warnings=["Heavy rain forecast along southern segment"],
        source=sample_source_ref,
    )


@pytest.fixture
def sample_incident(sample_destination: LatLon) -> IncidentInfo:
    """Sample emergency relief incident."""
    return IncidentInfo(
        incident_id="inc_anekal_001",
        commodity="drinking_water",
        required_quantity=100.0,
        unit="box",
        destination=sample_destination,
        priority="HIGH",
        description="Flash flood warning; community center cut off from drinking water.",
    )


# ---------------------------------------------------------------------------
# Phase 1 mock services
# ---------------------------------------------------------------------------

class MockWeatherService:
    """Mock WeatherService conforming to shared.contracts.WeatherService Protocol."""

    def __init__(self, observations: list[WeatherObservation] | None = None, error: Exception | None = None):
        self.observations = observations or []
        self.error = error
        self.calls: list[dict] = []

    async def get_forecast(self, location: LatLon, *, horizon_hours: int = 3) -> list[WeatherObservation]:
        self.calls.append({"location": location, "horizon_hours": horizon_hours})
        if self.error:
            raise self.error
        return self.observations


class MockHazardService:
    """Mock HazardService conforming to shared.contracts.HazardService Protocol."""

    def __init__(self, assessment: HazardAssessment | None = None, error: Exception | None = None):
        self.assessment = assessment
        self.error = error
        self.calls: list[list[WeatherObservation]] = []

    async def assess(self, observations: list[WeatherObservation]) -> HazardAssessment:
        self.calls.append(observations)
        if self.error:
            raise self.error
        assert self.assessment is not None
        return self.assessment


class MockSupplierService:
    """Mock SupplierService conforming to shared.contracts.SupplierService Protocol."""

    def __init__(
        self,
        suppliers_and_inventory: list[tuple[Supplier, InventoryItem]] | None = None,
        error: Exception | None = None,
    ):
        self.suppliers_and_inventory = suppliers_and_inventory or []
        self.error = error
        self.calls: list[dict] = []

    async def list_available(
        self, commodity: str, *, min_quantity: float = 0
    ) -> list[tuple[Supplier, InventoryItem]]:
        self.calls.append({"commodity": commodity, "min_quantity": min_quantity})
        if self.error:
            raise self.error
        return self.suppliers_and_inventory

    async def register_supplier(self, supplier: Supplier) -> Supplier:
        return supplier

    async def upsert_inventory(self, item: InventoryItem) -> InventoryItem:
        return item


class MockRoutingService:
    """Mock RoutingService conforming to shared.contracts.RoutingService Protocol."""

    def __init__(self, route_result: RouteResult | None = None, error: Exception | None = None):
        self.route_result = route_result
        self.error = error
        self.calls: list[RouteRequest] = []

    async def calculate_safe_route(self, request: RouteRequest) -> RouteResult:
        self.calls.append(request)
        if self.error:
            raise self.error
        assert self.route_result is not None
        return self.route_result


# ---------------------------------------------------------------------------
# Phase 2 mock services
# ---------------------------------------------------------------------------

class MockApprovalService:
    """Mock ApprovalService conforming to shared.contracts.ApprovalService Protocol."""

    def __init__(self, result_plan=None, error: Exception | None = None):
        self.result_plan = result_plan
        self.error = error
        self.calls: list = []

    async def decide(self, request) -> object:
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result_plan


class MockDispatchService:
    """Mock DispatchService conforming to shared.contracts.DispatchService Protocol."""

    def __init__(
        self,
        result: DispatchResult | None = None,
        errors: list[Exception] | None = None,
    ):
        """Args:
            result: The DispatchResult to return on success.
            errors: Optional list of exceptions to raise in order on successive calls.
                    Once exhausted, result is returned.
        """
        self.result = result
        self._errors = list(errors or [])
        self.calls: list = []
        self.acknowledgement_calls: list = []

    async def dispatch(self, request) -> DispatchResult:
        self.calls.append(request)
        if self._errors:
            exc = self._errors.pop(0)
            raise exc
        assert self.result is not None
        return self.result

    async def record_acknowledgement(self, ack) -> AuditEvent:
        self.acknowledgement_calls.append(ack)
        import uuid
        return AuditEvent(
            event_id=str(uuid.uuid4()),
            actor="driver",
            action="acknowledged",
            entity_type="delivery_plan",
            entity_id=ack.plan_id,
            outcome="ACKNOWLEDGED",
        )


class MockAuditService:
    """Mock AuditService conforming to shared.contracts.AuditService Protocol."""

    def __init__(self, error: Exception | None = None):
        self.events: list[AuditEvent] = []
        self.error = error

    async def append(self, event: AuditEvent) -> None:
        if self.error:
            raise self.error
        self.events.append(event)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_services(
    sample_weather_observations: list[WeatherObservation],
    sample_hazard_assessment: HazardAssessment,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_route_result: RouteResult,
) -> AgentServices:
    """Convenience fixture bundling mock services for end-to-end unit testing."""
    return AgentServices(
        weather_service=MockWeatherService(sample_weather_observations),
        hazard_service=MockHazardService(sample_hazard_assessment),
        supplier_service=MockSupplierService([(sample_supplier, sample_inventory)]),
        routing_service=MockRoutingService(sample_route_result),
    )


@pytest.fixture
def mock_audit_service() -> MockAuditService:
    """Standalone mock audit service fixture."""
    return MockAuditService()


@pytest.fixture
def sample_dispatch_result() -> DispatchResult:
    """A successful DispatchResult fixture."""
    return DispatchResult(
        dispatch_id="dsp_001",
        plan_id="plan_test",
        provider_message_id="tg_msg_001",
        status="SENT",
    )
