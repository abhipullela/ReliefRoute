"""API-level tests for approval/dispatch routes; use in the project test suite."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.approval_workflow import ApprovalDispatchWorkflow
from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
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

    async def transition_status(self, plan_id, status, *, expected_statuses):
        if self.plan.status not in expected_statuses:
            return None
        self.plan = self.plan.model_copy(update={"status": status})
        return self.plan


class FakeDispatches:
    def __init__(self, plans):
        self.plans = plans
        self.attempts = []
        self.acks = []

    async def begin_attempt(self, request):
        if self.plans.plan.status != PlanStatus.APPROVED:
            raise ReliefRouteError(
                ErrorCode.APPROVAL_REQUIRED, "Plan must be approved."
            )
        if self.attempts:
            raise AssertionError("Unexpected duplicate dispatch attempt.")
        self.attempts.append({"request": request, "status": "SENDING", "error": None})
        self.plans.plan = self.plans.plan.model_copy(
            update={"status": PlanStatus.DISPATCHING}
        )

    async def complete_attempt(self, request, *, provider_message_id):
        self.attempts[-1]["status"] = "SENT"
        self.plans.plan = self.plans.plan.model_copy(
            update={"status": PlanStatus.DISPATCHED}
        )
        return DispatchResult(
            dispatch_id="dispatch-api-1",
            plan_id=request.plan_id,
            provider_message_id=provider_message_id,
            status="SENT",
            attempted_at=datetime.now(UTC),
        )

    async def fail_attempt(self, request, *, error):
        self.attempts[-1].update(status="FAILED", error=error)
        self.plans.plan = self.plans.plan.model_copy(
            update={"status": PlanStatus.APPROVED}
        )

    async def record_acknowledgement(self, ack):
        if (
            self.plans.plan.status
            not in {
                PlanStatus.DISPATCHED,
                PlanStatus.ACKNOWLEDGED,
                PlanStatus.IN_TRANSIT,
            }
            or not any(
                attempt["status"] == "SENT"
                and attempt["request"].driver_id == ack.driver_id
                for attempt in self.attempts
            )
        ):
            raise ReliefRouteError(
                ErrorCode.NOT_FOUND, "No confirmed matching dispatch."
            )
        self.acks.append(ack)
        if ack.acknowledged and self.plans.plan.status == PlanStatus.DISPATCHED:
            self.plans.plan = self.plans.plan.model_copy(
                update={"status": PlanStatus.ACKNOWLEDGED}
            )
        return True


class FakeAudit:
    async def append(self, event):
        return None


@pytest.fixture
def client_and_services():
    plans = FakePlans(PlanStatus.NEEDS_APPROVAL)
    dispatches = FakeDispatches(plans)
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


def test_dispatch_and_acknowledgement_endpoints_update_plan(client_and_services):
    client, plans, _ = client_and_services
    app.state.notification_sender = _confirmed_sender
    approval = client.post(
        "/plans/p-api/approval",
        json={"approved": True, "approver_id": "reviewer-1"},
    )
    assert approval.status_code == 200, approval.text

    dispatched = client.post(
        "/plans/p-api/dispatch",
        json={
            "driver_id": "driver-1",
            "message": "Deliver supplies",
            "idempotency_key": "dispatch-api-success",
        },
    )
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["status"] == "SENT"
    assert plans.plan.status == PlanStatus.DISPATCHED

    acknowledged = client.post(
        "/plans/p-api/acknowledgement",
        json={"driver_id": "driver-1", "acknowledged": True},
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert plans.plan.status == PlanStatus.ACKNOWLEDGED


async def _confirmed_sender(_request):
    return {"status": "SENT", "provider_message_id": "telegram-message-1"}
