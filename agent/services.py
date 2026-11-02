"""Dependency injection container for backend services consumed by the agent.

Allows clean separation between Member A's orchestration and Member B's service
implementations (or mocks during isolated unit testing).
"""

from dataclasses import dataclass

from agent.planner import DefaultPlanningService
from shared.contracts import (
    ApprovalService,
    AuditService,
    DispatchService,
    HazardService,
    PlanningService,
    RoutingService,
    SupplierService,
    WeatherService,
)


@dataclass
class AgentServices:
    """Service interfaces consumed by the agent workflow."""

    weather_service: WeatherService | None = None
    hazard_service: HazardService | None = None
    supplier_service: SupplierService | None = None
    routing_service: RoutingService | None = None
    planning_service: PlanningService | None = None

    # Phase 2 services
    approval_service: ApprovalService | None = None
    dispatch_service: DispatchService | None = None
    audit_service: AuditService | None = None

    def get_planning_service(self) -> PlanningService:
        """Return injected planning service or default agent planning service."""
        if self.planning_service is not None:
            return self.planning_service
        return DefaultPlanningService()
