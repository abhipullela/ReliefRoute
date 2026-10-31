"""Deterministic guardrails and validation checks for ReliefRoute.

Enforces approval gates, data freshness, supplier status, inventory sufficiency,
route validity, and coordinate boundaries according to docs/05 and docs/09.
"""

from typing import TYPE_CHECKING

from agent.state import IncidentInfo, ValidationResult
from shared.models import (
    DeliveryPlan,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteResult,
    Supplier,
    utc_now,
)

if TYPE_CHECKING:
    from agent.state import AgentState


def validate_incident(incident: IncidentInfo | None) -> list[str]:
    """Validate that incident information is complete and well-formed."""
    errors: list[str] = []
    if incident is None:
        return ["Incident information is missing"]

    if not incident.incident_id or not incident.incident_id.strip():
        errors.append("Incident ID is required")
    if not incident.commodity or not incident.commodity.strip():
        errors.append("Incident commodity is required")
    if incident.required_quantity <= 0:
        errors.append("Incident required quantity must be greater than zero")
    if not incident.unit or not incident.unit.strip():
        errors.append("Incident unit of measure is required")
    if incident.destination is None:
        errors.append("Incident destination is required")
    else:
        if not (-90.0 <= incident.destination.latitude <= 90.0):
            errors.append(f"Invalid destination latitude: {incident.destination.latitude}")
        if not (-180.0 <= incident.destination.longitude <= 180.0):
            errors.append(f"Invalid destination longitude: {incident.destination.longitude}")

    return errors


def validate_hazard_assessment(hazard: HazardAssessment | None) -> list[str]:
    """Validate that hazard assessment exists, is fresh, and has valid sources."""
    errors: list[str] = []
    if hazard is None:
        return ["Hazard assessment is missing"]

    if not hazard.assessment_id or not hazard.assessment_id.strip():
        errors.append("Hazard assessment ID is required")
    if not hazard.sources:
        errors.append("Hazard assessment must include at least one source reference")
    else:
        for src in hazard.sources:
            if src.stale:
                errors.append(
                    f"Hazard assessment source from '{src.provider}' is marked stale beyond configured policy"
                )

    return errors


def validate_supplier_and_inventory(
    supplier: Supplier | None,
    inventory: InventoryItem | None,
    commodity: str,
    quantity: float,
) -> list[str]:
    """Validate supplier eligibility, inventory freshness, source type, and stock level."""
    errors: list[str] = []
    if supplier is None:
        return ["Supplier information is missing"]

    if not supplier.supplier_id or not supplier.supplier_id.strip():
        errors.append("Supplier ID is required")
    if not supplier.active:
        errors.append(f"Supplier '{supplier.name}' ({supplier.supplier_id}) is inactive")
    if supplier.location is None:
        errors.append("Supplier location is required")
    else:
        if not (-90.0 <= supplier.location.latitude <= 90.0):
            errors.append(f"Invalid supplier latitude: {supplier.location.latitude}")
        if not (-180.0 <= supplier.location.longitude <= 180.0):
            errors.append(f"Invalid supplier longitude: {supplier.location.longitude}")

    if inventory is None:
        errors.append("Inventory information is missing")
        return errors

    if inventory.source != "supplier_reported":
        errors.append(
            f"Inventory source '{inventory.source}' is not supplier-reported; inferred stock is forbidden"
        )
    if inventory.commodity.strip().lower() != commodity.strip().lower():
        errors.append(
            f"Inventory commodity '{inventory.commodity}' does not match requested '{commodity}'"
        )
    if inventory.quantity < quantity:
        errors.append(
            f"Inventory quantity {inventory.quantity} is insufficient for required quantity {quantity}"
        )
    if inventory.expires_at is not None and inventory.expires_at <= utc_now():
        errors.append(
            f"Inventory for '{inventory.commodity}' expired at {inventory.expires_at.isoformat()}"
        )

    return errors


def validate_route(
    route: RouteResult | None,
    origin: LatLon | None,
    destination: LatLon | None,
    hazard: HazardAssessment | None = None,
) -> tuple[list[str], list[str]]:
    """Validate route calculation, positive distance/duration, and polygon avoidance.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if route is None:
        return ["Route calculation is missing"], warnings

    if not route.provider or not route.provider.strip():
        errors.append("Route provider is required")
    if route.distance_m < 0:
        errors.append("Route distance cannot be negative")
    if route.duration_s < 0:
        errors.append("Route duration cannot be negative")
    if origin is None:
        errors.append("Route origin is missing")
    if destination is None:
        errors.append("Route destination is missing")

    if hazard and hazard.polygons and not route.avoids_requested_polygons:
        warnings.append(
            "Candidate route does not avoid requested hazard polygons according to provider response"
        )

    if route.warnings:
        warnings.extend(route.warnings)

    return errors, warnings


def validate_delivery_plan(
    plan: DeliveryPlan | None,
    hazard: HazardAssessment | None = None,
) -> list[str]:
    """Validate DeliveryPlan structure, approval gate, and idempotency key."""
    errors: list[str] = []
    if plan is None:
        return ["DeliveryPlan is missing"]

    if not plan.plan_id or not plan.plan_id.strip():
        errors.append("Plan ID is required")
    if not plan.idempotency_key or not plan.idempotency_key.strip():
        errors.append("Plan idempotency key is required")
    if not plan.approval_required:
        errors.append("Plan must require human approval (approval_required must be True)")
    if plan.quantity <= 0:
        errors.append("Plan delivery quantity must be greater than zero")
    if not plan.commodity or not plan.commodity.strip():
        errors.append("Plan commodity is required")
    if plan.origin is None:
        errors.append("Plan origin is required")
    if plan.destination is None:
        errors.append("Plan destination is required")
    if plan.route is None:
        errors.append("Plan must include a calculated route")
    if hazard and plan.hazard_assessment_id != hazard.assessment_id:
        errors.append(
            f"Plan hazard assessment ID '{plan.hazard_assessment_id}' does not match active assessment '{hazard.assessment_id}'"
        )
    if not plan.rationale:
        errors.append("Plan must include at least one rationale statement")
    if not plan.source_refs:
        errors.append("Plan must include at least one source reference")

    return errors


def validate_plan_guardrails(state: "AgentState") -> ValidationResult:
    """Run all deterministic guardrail checks on the current agent state."""
    errors: list[str] = []
    warnings: list[str] = []

    # 0. Upstream pipeline health
    if state.get("workflow_status") == "DEGRADED":
        errors.append("Guardrail check failed: upstream weather monitoring is in a DEGRADED state")

    # 1. Incident
    incident = state.get("incident")
    errors.extend(validate_incident(incident))

    # 2. Hazard Assessment
    hazard = state.get("hazard_assessment")
    errors.extend(validate_hazard_assessment(hazard))

    # 3. Supplier & Inventory
    if incident is not None:
        supplier = state.get("selected_supplier")
        inventory = state.get("selected_inventory")
        errors.extend(
            validate_supplier_and_inventory(
                supplier,
                inventory,
                incident.commodity,
                incident.required_quantity,
            )
        )

    # 4. Route
    route = state.get("route")
    selected_supplier = state.get("selected_supplier")
    origin = selected_supplier.location if selected_supplier is not None else None
    destination = incident.destination if incident else None
    route_errors, route_warnings = validate_route(route, origin, destination, hazard)
    errors.extend(route_errors)
    warnings.extend(route_warnings)

    # 5. DeliveryPlan
    plan = state.get("delivery_plan")
    errors.extend(validate_delivery_plan(plan, hazard))

    return ValidationResult(
        is_valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        checked_at=utc_now(),
    )
