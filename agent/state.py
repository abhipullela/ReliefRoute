"""Agent state definitions for ReliefRoute decision-making workflow."""

from datetime import datetime
from typing import Any, TypedDict

from pydantic import Field

from shared.models import (
    ContractModel,
    DeliveryPlan,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteResult,
    SourceRef,
    Supplier,
    WeatherObservation,
    utc_now,
)


class IncidentInfo(ContractModel):
    """Information about an emergency relief request / incident."""

    incident_id: str
    commodity: str
    required_quantity: float = Field(gt=0)
    unit: str
    destination: LatLon
    reported_at: datetime = Field(default_factory=utc_now)
    priority: str = "NORMAL"
    description: str | None = None


class ValidationResult(ContractModel):
    """Deterministic validation results for guardrail checks."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)


class WorkflowStatus:
    """Standard workflow status codes for agent orchestration."""

    INITIALIZED = "INITIALIZED"
    MONITORING = "MONITORING"
    MONITORED = "MONITORED"
    ASSESSING = "ASSESSING"
    ASSESSED = "ASSESSED"
    PLANNING = "PLANNING"
    PLANNED = "PLANNED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"  # Successful planning state
    NEEDS_INFO = "NEEDS_INFO"  # Invalid plan due to missing information
    FAILED = "FAILED"  # General failure state
    DEGRADED = "DEGRADED"  # Upstream provider unavailable
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"  # No eligible supplier/route found
    BLOCKED = "BLOCKED"  # Blocked by guardrails


class AgentState(TypedDict, total=False):
    """The central state dictionary flowing through LangGraph."""

    incident: IncidentInfo | None
    location: LatLon | None
    weather_observations: list[WeatherObservation]
    hazard_assessment: HazardAssessment | None
    available_suppliers: list[tuple[Supplier, InventoryItem]]
    selected_supplier: Supplier | None
    selected_inventory: InventoryItem | None
    route: RouteResult | None
    delivery_plan: DeliveryPlan | None
    workflow_status: str
    validation_results: ValidationResult | None
    errors: list[str]
    missing_info: list[str]
    sources: list[SourceRef]
    created_at: str
    updated_at: str


def create_initial_state(
    incident: IncidentInfo | dict[str, Any] | None = None,
    location: LatLon | dict[str, Any] | None = None,
) -> AgentState:
    """Initialize an AgentState dictionary with valid defaults and timestamps."""
    resolved_incident: IncidentInfo | None = None
    if isinstance(incident, dict):
        resolved_incident = IncidentInfo(**incident)
    elif isinstance(incident, IncidentInfo):
        resolved_incident = incident

    resolved_location: LatLon | None = None
    if isinstance(location, dict):
        resolved_location = LatLon(**location)
    elif isinstance(location, LatLon):
        resolved_location = location
    elif resolved_incident is not None:
        resolved_location = resolved_incident.destination

    now_iso = utc_now().isoformat()

    return {
        "incident": resolved_incident,
        "location": resolved_location,
        "weather_observations": [],
        "hazard_assessment": None,
        "available_suppliers": [],
        "selected_supplier": None,
        "selected_inventory": None,
        "route": None,
        "delivery_plan": None,
        "workflow_status": WorkflowStatus.INITIALIZED,
        "validation_results": None,
        "errors": [],
        "missing_info": [],
        "sources": [],
        "created_at": now_iso,
        "updated_at": now_iso,
    }
