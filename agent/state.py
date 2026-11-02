"""Agent state definitions for ReliefRoute decision-making workflow."""

from datetime import datetime
from typing import Any, TypedDict

from pydantic import Field

from shared.models import (
    ApprovalRequest,
    CitizenReport,
    ContractModel,
    DeliveryPlan,
    DispatchResult,
    ExtractedEmergencyReport,
    HazardAssessment,
    InventoryItem,
    LatLon,
    ReportExtractionMetadata,
    ReportValidationResult,
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
    VALIDATED = "VALIDATED"            # Successful planning; pending human approval
    NEEDS_INFO = "NEEDS_INFO"          # Invalid plan due to missing information
    FAILED = "FAILED"                  # General failure state
    DEGRADED = "DEGRADED"              # Upstream provider unavailable
    NO_FEASIBLE_PLAN = "NO_FEASIBLE_PLAN"  # No eligible supplier/route found
    BLOCKED = "BLOCKED"                # Blocked by guardrails

    # Phase 2 statuses
    AWAITING_APPROVAL = "AWAITING_APPROVAL"   # Waiting for human decision
    APPROVED = "APPROVED"                      # Human approved; ready for dispatch
    REJECTED = "REJECTED"                      # Human rejected; dispatch blocked
    DISPATCHING = "DISPATCHING"                # Dispatch in progress
    DISPATCHED = "DISPATCHED"                  # Successfully dispatched
    DISPATCH_FAILED = "DISPATCH_FAILED"        # Dispatch attempt failed
    VERIFYING = "VERIFYING"                    # Awaiting driver acknowledgement
    COMPLETED = "COMPLETED"                    # Delivery confirmed complete
    REPLANNING = "REPLANNING"                  # Replanning due to changed conditions


# Statuses that indicate an upstream failure which must propagate downstream
_UPSTREAM_FAILURE_STATUSES = frozenset([
    WorkflowStatus.DEGRADED,
    WorkflowStatus.NEEDS_INFO,
    WorkflowStatus.FAILED,
])

# Error codes that should NOT be retried
_NON_RETRYABLE_CODES = frozenset([
    "UPSTREAM_AUTH_FAILED",
    "VALIDATION_ERROR",
    "CONFLICT",
])

# Max replanning attempts before surfacing FAILED_NEEDS_OPERATOR
MAX_REPLAN_ATTEMPTS: int = 3

# Retry policy: 1 initial + up to 2 retries = 3 total attempts
MAX_DISPATCH_ATTEMPTS: int = 3


class AgentState(TypedDict, total=False):
    """The central state dictionary flowing through LangGraph."""

    # Core incident and location
    incident: IncidentInfo | None
    location: LatLon | None

    # Planning inputs
    weather_observations: list[WeatherObservation]
    hazard_assessment: HazardAssessment | None
    available_suppliers: list[tuple[Supplier, InventoryItem]]
    selected_supplier: Supplier | None
    selected_inventory: InventoryItem | None
    route: RouteResult | None
    delivery_plan: DeliveryPlan | None

    # Validation
    validation_results: ValidationResult | None

    # Phase 2: Approval, dispatch, verification
    approval_request: ApprovalRequest | None   # The human decision record
    dispatch_result: DispatchResult | None      # Latest dispatch outcome
    dispatch_attempts: int                       # Running retry count

    # Workflow tracking
    workflow_status: str
    replan_count: int                            # Bounded replan attempts
    errors: list[str]
    missing_info: list[str]
    sources: list[SourceRef]
    audit_events: list[dict[str, Any]]           # Serialised AuditEvent records
    created_at: str
    updated_at: str
        # AI-powered citizen report processing
    citizen_report: CitizenReport | None
    extracted_report: ExtractedEmergencyReport | None
    extraction_metadata: ReportExtractionMetadata | None
    report_validation: ReportValidationResult | None


def create_initial_state(
    incident: IncidentInfo | dict[str, Any] | None = None,
    location: LatLon | dict[str, Any] | None = None,
    citizen_report: CitizenReport | None = None,
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
        "approval_request": None,
        "dispatch_result": None,
        "dispatch_attempts": 0,
        "replan_count": 0,
        "errors": [],
        "missing_info": [],
        "sources": [],
        "audit_events": [],
        "created_at": now_iso,
        "updated_at": now_iso,
        "citizen_report": citizen_report,
        "extracted_report": None,
        "extraction_metadata": None,
        "report_validation": None,
    }
