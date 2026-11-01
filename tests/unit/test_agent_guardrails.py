"""Unit tests for deterministic guardrails and validation."""

from datetime import UTC, datetime, timedelta

from agent.guardrails import (
    validate_delivery_plan,
    validate_hazard_assessment,
    validate_incident,
    validate_plan_guardrails,
    validate_route,
    validate_supplier_and_inventory,
)
from agent.state import IncidentInfo, create_initial_state
from shared.enums import RiskLevel
from shared.models import (
    DeliveryPlan,
    GeoJSONPolygon,
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteResult,
    SourceRef,
    Supplier,
)


def test_validate_incident_valid(sample_incident: IncidentInfo):
    """Valid incident produces no validation errors."""
    errors = validate_incident(sample_incident)
    assert errors == []


def test_validate_incident_missing():
    """Missing incident produces an error."""
    errors = validate_incident(None)
    assert "Incident information is missing" in errors


def test_validate_hazard_assessment_valid(sample_hazard_assessment: HazardAssessment):
    """Valid hazard assessment passes with zero errors."""
    errors = validate_hazard_assessment(sample_hazard_assessment)
    assert errors == []


def test_validate_hazard_assessment_stale_source(sample_source_ref: SourceRef):
    """Hazard assessment with stale source fails validation per docs/09."""
    stale_ref = sample_source_ref.model_copy(update={"stale": True})
    hazard = HazardAssessment(
        assessment_id="hz_stale_01",
        risk_level=RiskLevel.HIGH,
        sources=[stale_ref],
        rationale=["Forecast model"],
        limitations=[],
    )
    errors = validate_hazard_assessment(hazard)
    assert any("marked stale" in err for err in errors)


def test_validate_hazard_assessment_missing_sources():
    """Hazard assessment without source references fails validation."""
    hazard = HazardAssessment(
        assessment_id="hz_nosrc_01",
        risk_level=RiskLevel.LOW,
        sources=[],
        rationale=["No source info"],
        limitations=[],
    )
    errors = validate_hazard_assessment(hazard)
    assert "Hazard assessment must include at least one source reference" in errors


def test_validate_supplier_and_inventory_valid(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Valid supplier and fresh supplier-reported inventory pass validation."""
    errors = validate_supplier_and_inventory(
        supplier=sample_supplier,
        inventory=sample_inventory,
        commodity="drinking_water",
        quantity=50.0,
    )
    assert errors == []


def test_validate_supplier_inactive(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Inactive supplier is rejected by guardrails."""
    inactive_supplier = sample_supplier.model_copy(update={"active": False})
    errors = validate_supplier_and_inventory(
        supplier=inactive_supplier,
        inventory=sample_inventory,
        commodity="drinking_water",
        quantity=50.0,
    )
    assert any("inactive" in err for err in errors)


def test_validate_inventory_forbidden_source(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Inventory not reported directly by supplier (e.g., mandi data) is rejected."""
    mandi_inventory = sample_inventory.model_copy(update={"source": "mandi_arrival_estimated"})
    errors = validate_supplier_and_inventory(
        supplier=sample_supplier,
        inventory=mandi_inventory,
        commodity="drinking_water",
        quantity=50.0,
    )
    assert any("not supplier-reported" in err for err in errors)


def test_validate_inventory_insufficient_quantity(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Inventory quantity less than required is rejected."""
    errors = validate_supplier_and_inventory(
        supplier=sample_supplier,
        inventory=sample_inventory,  # 500.0 available
        commodity="drinking_water",
        quantity=1000.0,  # 1000.0 requested
    )
    assert any("insufficient" in err for err in errors)


def test_validate_inventory_expired(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
):
    """Expired inventory is rejected."""
    expired_inv = sample_inventory.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(hours=1)}
    )
    errors = validate_supplier_and_inventory(
        supplier=sample_supplier,
        inventory=expired_inv,
        commodity="drinking_water",
        quantity=50.0,
    )
    assert any("expired" in err for err in errors)


def test_validate_route_valid(
    sample_route_result: RouteResult,
    sample_origin: LatLon,
    sample_destination: LatLon,
):
    """Valid route calculation passes validation."""
    clean_route = sample_route_result.model_copy(update={"warnings": []})
    errors, warnings = validate_route(
        route=clean_route,
        origin=sample_origin,
        destination=sample_destination,
    )
    assert errors == []
    assert warnings == []


def test_validate_route_polygon_warning(
    sample_route_result: RouteResult,
    sample_origin: LatLon,
    sample_destination: LatLon,
    sample_source_ref: SourceRef,
):
    """Route that fails to avoid hazard polygons emits a visible warning."""
    hazard = HazardAssessment(
        assessment_id="hz_poly_01",
        risk_level=RiskLevel.HIGH,
        polygons=[
            GeoJSONPolygon(
                type="Polygon",
                coordinates=[
                    [[77.6, 12.8], [77.7, 12.8], [77.7, 12.9], [77.6, 12.9], [77.6, 12.8]]
                ],
            )
        ],
        sources=[sample_source_ref],
        rationale=["Flood area mapped"],
        limitations=[],
    )
    # Route that did not avoid polygons
    route_not_avoided = sample_route_result.model_copy(
        update={"avoids_requested_polygons": False}
    )
    errors, warnings = validate_route(
        route=route_not_avoided,
        origin=sample_origin,
        destination=sample_destination,
        hazard=hazard,
    )
    assert errors == []
    assert any("does not avoid requested hazard polygons" in w for w in warnings)


def test_validate_delivery_plan_unapproved_flag_rejected(
    sample_origin: LatLon,
    sample_destination: LatLon,
    sample_route_result: RouteResult,
    sample_source_ref: SourceRef,
):
    """DeliveryPlan with approval_required=False is rejected by guardrails."""
    plan = DeliveryPlan(
        plan_id="plan_test_01",
        supplier_id="sup_01",
        commodity="drinking_water",
        quantity=50.0,
        unit="box",
        origin=sample_origin,
        destination=sample_destination,
        route=sample_route_result,
        hazard_assessment_id="hz_01",
        approval_required=False,  # Violation of safety policy
        idempotency_key="key_01",
        rationale=["Planned"],
        source_refs=[sample_source_ref],
    )
    errors = validate_delivery_plan(plan)
    assert any("approval_required must be True" in err for err in errors)


def test_validate_plan_guardrails_integration(
    sample_incident: IncidentInfo,
    sample_hazard_assessment: HazardAssessment,
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_route_result: RouteResult,
    sample_source_ref: SourceRef,
):
    """validate_plan_guardrails passes when all components are valid."""
    plan = DeliveryPlan(
        plan_id="plan_valid_01",
        supplier_id=sample_supplier.supplier_id,
        commodity=sample_incident.commodity,
        quantity=sample_incident.required_quantity,
        unit=sample_incident.unit,
        origin=sample_supplier.location,
        destination=sample_incident.destination,
        route=sample_route_result,
        hazard_assessment_id=sample_hazard_assessment.assessment_id,
        approval_required=True,
        idempotency_key="plan_idem_12345678",
        rationale=["Valid rationale"],
        source_refs=[sample_source_ref],
    )

    state = create_initial_state(incident=sample_incident)
    state["hazard_assessment"] = sample_hazard_assessment
    state["selected_supplier"] = sample_supplier
    state["selected_inventory"] = sample_inventory
    state["route"] = sample_route_result
    state["delivery_plan"] = plan

    res = validate_plan_guardrails(state)
    assert res.is_valid
    assert len(res.errors) == 0
