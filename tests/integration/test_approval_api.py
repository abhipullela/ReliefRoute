"""API-level tests for approval/dispatch routes; use in the project test suite."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.approval_workflow import ApprovalDispatchWorkflow
from shared.enums import PlanStatus
from shared.models import DeliveryPlan, DispatchResult, LatLon


class FakePlans:
    def __init__(self, status: PlanStatus):
        self.plan = DeliveryPlan(
            plan_id="p-api",
            supplier_id="supplier-1",
            commodity="rice",
            quantity=10,
            unit="kg",
            origin=LatLon(latitude=12.0, longitude=77.0),
            destination=LatLon(latitude=12.1, longitude=77.1),
            hazard_assessment_id="hazard-1",
            status=status,
            idempotency_key="plan-api-1",
            rationale=["test fixture"],
        )

    async def get_plan(self, plan_id):
        return self.plan if plan_id == self.plan.plan_id else None

    async def update_status(self, plan_id, status):
        self.plan = self.plan.model_copy(update={"status": status})
        return self.plan


class FakeDispatches:
    def __init__(self):
        self.attempts = []
        self.acks = []

    async def record_attempt(self, request, *, status, provider_message_id=None, error=None):
        self.attempts.append({"request": request, "status": status, "error": error})
        return DispatchResult(
            dispatch_id="dispatch-api-1",
            plan_id=request.plan_id,
            provider_message_id=provider_message_id,
            status=status,
            attempted_at=datetime.now(timezone.utc),
        )

    async def record_acknowledgement(self, ack):
        self.acks.append(ack)


class FakeAudit:
    async def append(self, event):
        return None


@pytest.fixture
def client_and_services():
    plans = FakePlans(PlanStatus.NEEDS_APPROVAL)
    dispatches = FakeDispatches()
    app.state.approval_workflow = ApprovalDispatchWorkflow(
        plans=plans, dispatches=dispatches, audit=FakeAudit()
    )
    app.state.notification_sender = None
    with TestClient(app) as client:
        # The lifespan initializes app state; reinject the fakes after startup.
        app.state.approval_workflow = ApprovalDispatchWorkflow(
            plans=plans, dispatches=dispatches, audit=FakeAudit()
        )
        app.state.notification_sender = None
        yield client, plans, dispatches


def test_approval_endpoint_updates_plan(client_and_services):
    client, plans, _ = client_and_services
    response = client.post(
        "/plans/p-api/approval",
        json={"approved": True, "approver_id": "reviewer-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "APPROVED"
    assert plans.plan.status == PlanStatus.APPROVED


def test_dispatch_endpoint_rejects_unapproved_plan(client_and_services):
    client, _, dispatches = client_and_services
    response = client.post(
        "/plans/p-api/dispatch",
        json={"driver_id": "driver-1", "message": "Deliver supplies", "idempotency_key": "dispatch-api-1"},
    )
    assert response.status_code == 409, response.text
    assert dispatches.attempts == []


def test_unconfigured_provider_is_not_reported_as_success(client_and_services):
    client, plans, dispatches = client_and_services
    plans.plan = plans.plan.model_copy(update={"status": PlanStatus.APPROVED})
    response = client.post(
        "/plans/p-api/dispatch",
        json={"driver_id": "driver-1", "message": "Deliver supplies", "idempotency_key": "dispatch-api-2"},
    )
    assert response.status_code == 503, response.text
    assert dispatches.attempts[0]["status"] == "FAILED"
    assert plans.plan.status == PlanStatus.APPROVED
