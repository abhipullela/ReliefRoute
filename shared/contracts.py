from typing import Protocol

from shared.models import (
    ApprovalRequest,
    AuditEvent,
    DeliveryPlan,
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
    DriverLocation,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteRequest,
    RouteResult,
    Supplier,
    WeatherObservation,
)


class WeatherService(Protocol):
    async def get_forecast(self, location: LatLon, *, horizon_hours: int = 3) -> list[WeatherObservation]: ...

class HazardService(Protocol):
    async def assess(self, observations: list[WeatherObservation]) -> HazardAssessment: ...

class SupplierService(Protocol):
    async def list_available(self, commodity: str, *, min_quantity: float = 0) -> list[tuple[Supplier, InventoryItem]]: ...
    async def register_supplier(self, supplier: Supplier) -> Supplier: ...
    async def upsert_inventory(self, item: InventoryItem) -> InventoryItem: ...

class RoutingService(Protocol):
    async def calculate_safe_route(self, request: RouteRequest) -> RouteResult: ...

class TelemetryService(Protocol):
    async def record_location(self, location: DriverLocation) -> DriverLocation: ...
    async def latest_location(self, driver_id: str) -> DriverLocation | None: ...

class PlanningService(Protocol):
    async def create_plan(self, *, supplier: Supplier, inventory: InventoryItem,
                          origin: LatLon, destination: LatLon,
                          hazard: HazardAssessment) -> DeliveryPlan: ...

class ApprovalService(Protocol):
    async def decide(self, request: ApprovalRequest) -> DeliveryPlan: ...

class DispatchService(Protocol):
    async def dispatch(self, request: DispatchRequest) -> DispatchResult: ...
    async def record_acknowledgement(self, ack: DriverAcknowledgement) -> bool: ...

class AuditService(Protocol):
    async def append(self, event: AuditEvent) -> None: ...
