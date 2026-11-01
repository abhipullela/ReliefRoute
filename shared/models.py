from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shared.enums import (
    EmergencyUrgency,
    ExtractionStatus,
    PlanStatus,
    RiskLevel,
    VerificationStatus,
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class LatLon(ContractModel):
    # Internal point convention: named fields prevent coordinate-order ambiguity.
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class GeoJSONPolygon(ContractModel):
    # GeoJSON positions MUST be [longitude, latitude]. Polygon must be valid and closed.
    type: str = "Polygon"
    coordinates: list[list[list[float]]]
    @field_validator("type")
    @classmethod
    def polygon_only(cls, value: str) -> str:
        if value != "Polygon":
            raise ValueError("Only GeoJSON Polygon is supported by v1")
        return value

class SourceRef(ContractModel):
    provider: str
    url: str | None = None
    retrieved_at: datetime
    observed_at: datetime | None = None
    stale: bool = False
    notes: str | None = None

class ServiceError(ContractModel):
    code: str
    message: str
    retryable: bool = False
    provider: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)

class WeatherObservation(ContractModel):
    location: LatLon
    forecast_start: datetime
    forecast_end: datetime
    precipitation_mm: float = Field(ge=0)
    source: SourceRef
    # Forecast is a forecast, not proof of flooding or road closure.

class HazardAssessment(ContractModel):
    assessment_id: str
    generated_at: datetime = Field(default_factory=utc_now)
    risk_level: RiskLevel
    polygons: list[GeoJSONPolygon] = Field(default_factory=list)
    sources: list[SourceRef]
    rationale: list[str]
    limitations: list[str]
    # Empty polygons means no polygon generated; it does NOT mean no hazard.

class Supplier(ContractModel):
    supplier_id: str
    name: str
    location: LatLon
    contact_channel: str = "telegram"
    contact_handle: str
    verified_at: datetime | None = None
    active: bool = True

class InventoryItem(ContractModel):
    supplier_id: str
    commodity: str
    quantity: float = Field(gt=0)
    unit: str
    updated_at: datetime
    expires_at: datetime | None = None
    source: str = "supplier_reported"
    # Never infer this from mandi arrival/price data.

class DriverLocation(ContractModel):
    driver_id: str
    location: LatLon
    observed_at: datetime
    source: str
    accuracy_m: float | None = Field(default=None, ge=0)
    consented: bool = True

class RouteRequest(ContractModel):
    origin: LatLon
    destination: LatLon
    avoid_polygons: list[GeoJSONPolygon] = Field(default_factory=list)
    profile: str = "driving-car"
    departure_time: datetime = Field(default_factory=utc_now)

class RouteResult(ContractModel):
    provider: str
    geometry: dict[str, Any] | None = None  # GeoJSON LineString when available
    distance_m: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    avoids_requested_polygons: bool
    risk_level: RiskLevel
    warnings: list[str] = Field(default_factory=list)
    source: SourceRef

class DeliveryPlan(ContractModel):
    plan_id: str
    created_at: datetime = Field(default_factory=utc_now)
    supplier_id: str
    commodity: str
    quantity: float = Field(gt=0)
    unit: str
    origin: LatLon
    destination: LatLon
    route: RouteResult | None = None
    hazard_assessment_id: str
    status: PlanStatus = PlanStatus.DRAFT
    approval_required: bool = True
    idempotency_key: str
    rationale: list[str]
    source_refs: list[SourceRef] = Field(default_factory=list)

class ApprovalRequest(ContractModel):
    plan_id: str
    approved: bool
    approver_id: str
    comment: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)

class DispatchRequest(ContractModel):
    plan_id: str
    driver_id: str
    message: str
    idempotency_key: str

class DispatchResult(ContractModel):
    dispatch_id: str
    plan_id: str
    provider_message_id: str | None = None
    status: str  # SENT, FAILED; acknowledgement is a separate event.
    attempted_at: datetime = Field(default_factory=utc_now)
    error: ServiceError | None = None

class DriverAcknowledgement(ContractModel):
    plan_id: str
    driver_id: str
    acknowledged: bool
    received_at: datetime = Field(default_factory=utc_now)
    message: str | None = None

class AuditEvent(ContractModel):
    event_id: str
    occurred_at: datetime = Field(default_factory=utc_now)
    actor: str
    action: str
    entity_type: str
    entity_id: str
    outcome: str
    details: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)

class CitizenReport(ContractModel):
    report_id: str
    channel: str = "telegram"
    sender_handle: str | None = None
    raw_text: str
    raw_location_text: str | None = None
    provided_location: LatLon | None = None
    reported_at: datetime = Field(default_factory=utc_now)

class ExtractedEmergency(ContractModel):
    raw_report_id: str
    commodity: str
    estimated_quantity: float | None = None
    quantity_unspecified: bool = False
    unit: str | None = None
    location_text: str
    resolved_destination: LatLon | None = None
    urgency: EmergencyUrgency = EmergencyUrgency.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    extraction_notes: list[str] = Field(default_factory=list)
class ExtractedNeed(ContractModel):
    commodity: str

    quantity: float | None = Field(default=None, gt=0)

    unit: str | None = None

    evidence: list[str] = Field(default_factory=list)
class ExtractedEmergencyReport(ContractModel):
    report_id: str

    incident_type: str | None = None

    location_description: str | None = None

    coordinates: LatLon | None = None

    people_affected: int | None = Field(default=None, ge=0)

    affected_households: int | None = Field(default=None, ge=0)
    needs: list[ExtractedNeed] = Field(default_factory=list)

    reported_conditions: list[str] = Field(default_factory=list)

    reported_urgency: EmergencyUrgency = EmergencyUrgency.UNKNOWN

    missing_information: list[str] = Field(default_factory=list)

    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    verification_status: VerificationStatus = VerificationStatus.PENDING

    extracted_at: datetime = Field(default_factory=utc_now)

class ReportExtractionMetadata(ContractModel):
    report_id: str

    provider: str

    model: str

    status: ExtractionStatus = ExtractionStatus.PENDING

    extracted_at: datetime = Field(default_factory=utc_now)

    errors: list[str] = Field(default_factory=list)
class ReportValidationResult(ContractModel):
    report_id: str

    structurally_valid: bool

    validation_issues: list[str] = Field(default_factory=list)

    clarification_fields: list[str] = Field(default_factory=list)
