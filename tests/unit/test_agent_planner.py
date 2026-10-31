"""Unit tests for agent planner and DeliveryPlan generation."""

import pytest

from agent.planner import DefaultPlanningService, compute_plan_idempotency_key
from shared.enums import PlanStatus
from shared.models import (
    HazardAssessment,
    InventoryItem,
    LatLon,
    RouteResult,
    Supplier,
)


def test_compute_plan_idempotency_key_deterministic(
    sample_origin: LatLon,
    sample_destination: LatLon,
):
    """Verify that compute_plan_idempotency_key produces stable, repeatable outputs."""
    key1 = compute_plan_idempotency_key(
        supplier_id="sup_01",
        commodity="milk",
        origin=sample_origin,
        destination=sample_destination,
        hazard_assessment_id="hz_01",
    )
    key2 = compute_plan_idempotency_key(
        supplier_id="sup_01",
        commodity="milk",
        origin=sample_origin,
        destination=sample_destination,
        hazard_assessment_id="hz_01",
    )
    assert key1 == key2
    assert key1.startswith("plan_idem_")


def test_compute_plan_idempotency_key_differentiates_inputs(
    sample_origin: LatLon,
    sample_destination: LatLon,
):
    """Verify that different parameters produce distinct idempotency keys."""
    key_orig = compute_plan_idempotency_key(
        supplier_id="sup_01",
        commodity="milk",
        origin=sample_origin,
        destination=sample_destination,
        hazard_assessment_id="hz_01",
    )
    key_diff_commodity = compute_plan_idempotency_key(
        supplier_id="sup_01",
        commodity="rice",
        origin=sample_origin,
        destination=sample_destination,
        hazard_assessment_id="hz_01",
    )
    assert key_orig != key_diff_commodity


@pytest.mark.asyncio
async def test_create_plan_success(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_hazard_assessment: HazardAssessment,
    sample_route_result: RouteResult,
    sample_destination: LatLon,
):
    """Verify DefaultPlanningService generates a complete, valid DeliveryPlan."""
    planner = DefaultPlanningService()
    plan = await planner.create_plan(
        supplier=sample_supplier,
        inventory=sample_inventory,
        origin=sample_supplier.location,
        destination=sample_destination,
        hazard=sample_hazard_assessment,
        route=sample_route_result,
        requested_quantity=100.0,
    )

    assert plan.plan_id.startswith("plan_")
    assert plan.supplier_id == sample_supplier.supplier_id
    assert plan.commodity == sample_inventory.commodity
    assert plan.quantity == 100.0
    assert plan.unit == sample_inventory.unit
    assert plan.status == PlanStatus.DRAFT
    assert plan.approval_required is True
    assert plan.route == sample_route_result
    assert plan.hazard_assessment_id == sample_hazard_assessment.assessment_id
    assert len(plan.rationale) >= 3
    assert any("Selected active supplier" in r for r in plan.rationale)
    assert any("Candidate route calculated" in r for r in plan.rationale)
    assert len(plan.source_refs) >= 1


@pytest.mark.asyncio
async def test_create_plan_quantity_clamping(
    sample_supplier: Supplier,
    sample_inventory: InventoryItem,
    sample_hazard_assessment: HazardAssessment,
    sample_destination: LatLon,
):
    """Verify allocated quantity cannot exceed available inventory."""
    planner = DefaultPlanningService()
    # sample_inventory has 500.0
    plan = await planner.create_plan(
        supplier=sample_supplier,
        inventory=sample_inventory,
        origin=sample_supplier.location,
        destination=sample_destination,
        hazard=sample_hazard_assessment,
        requested_quantity=999.0,  # Exceeds 500.0
    )
    assert plan.quantity == 500.0
