"""Integration test for delivery-plan persistence."""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import psycopg
from dotenv import load_dotenv

from services.plans import PostgreSQLPlanningStore
from shared.enums import PlanStatus, RiskLevel
from shared.models import (
    DeliveryPlan,
    HazardAssessment,
    LatLon,
    RouteResult,
    SourceRef,
)

load_dotenv()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env")

    store = PostgreSQLPlanningStore(database_url)
    suffix = uuid.uuid4().hex
    plan_id = f"plan-test-{suffix}"
    idempotency_key = f"plan-test-key-{suffix}"

    now = datetime.now(UTC)
    source = SourceRef(
        provider="integration_test",
        retrieved_at=now,
        observed_at=now,
    )
    hazard = HazardAssessment(
        assessment_id=f"hazard-test-{suffix}",
        risk_level=RiskLevel.UNKNOWN,
        sources=[source],
        rationale=["Integration test only."],
        limitations=["Not a real hazard assessment."],
    )
    route = RouteResult(
        provider="integration_test",
        distance_m=1000,
        duration_s=300,
        avoids_requested_polygons=False,
        risk_level=RiskLevel.UNKNOWN,
        warnings=["Integration test route; not for navigation."],
        source=source,
    )
    plan = DeliveryPlan(
        plan_id=plan_id,
        supplier_id=f"supplier-test-{suffix}",
        commodity="test-commodity",
        quantity=1,
        unit="unit",
        origin=LatLon(latitude=12.9716, longitude=77.5946),
        destination=LatLon(latitude=12.9352, longitude=77.6245),
        route=route,
        hazard_assessment_id=hazard.assessment_id,
        status=PlanStatus.DRAFT,
        approval_required=True,
        idempotency_key=idempotency_key,
        rationale=["Persistence integration test."],
        source_refs=[source],
    )

    try:
        saved = await store.save_plan(plan)
        assert saved.plan_id == plan_id
        print("PASS: plan persisted.")

        repeated = await store.save_plan(plan)
        assert repeated.plan_id == plan_id
        print("PASS: idempotent retry returns existing plan.")

        fetched = await store.get_plan(plan_id)
        assert fetched is not None
        assert fetched.commodity == "test-commodity"
        print("PASS: plan retrieved.")

        updated = await store.update_status(plan_id, PlanStatus.NEEDS_APPROVAL)
        assert updated.status == PlanStatus.NEEDS_APPROVAL
        print("PASS: plan status updated.")

    finally:
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            await connection.execute(
                "DELETE FROM plans WHERE plan_id = %s",
                (plan_id,),
            )

        print("Test records cleaned up.")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)