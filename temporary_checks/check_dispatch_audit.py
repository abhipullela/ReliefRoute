"""Integration checks for dispatch persistence and audit logging."""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

import psycopg
from dotenv import load_dotenv

from services.audit import PostgreSQLAuditService
from services.dispatch import PostgreSQLDispatchService
from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import (
    AuditEvent,
    DispatchRequest,
    DriverAcknowledgement,
)

load_dotenv()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env")

    dispatch_service = PostgreSQLDispatchService(database_url)
    audit_service = PostgreSQLAuditService(database_url)

    suffix = uuid.uuid4().hex
    plan_id = f"dispatch-test-plan-{suffix}"
    driver_id = f"dispatch-test-driver-{suffix}"
    dispatch_key = f"dispatch-test-key-{suffix}"
    event_id = f"audit-test-{suffix}"

    request = DispatchRequest(
        plan_id=plan_id,
        driver_id=driver_id,
        message="Integration test only. Do not send to a real driver.",
        idempotency_key=dispatch_key,
    )

    dispatch_id = None

    try:
        # The dispatches table references plans, so create a temporary parent.
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            await connection.execute(
                """
                INSERT INTO plans (
                    plan_id, status, idempotency_key, payload
                )
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    plan_id,
                    "DRAFT",
                    f"parent-plan-key-{suffix}",
                    json.dumps({"plan_id": plan_id, "status": "DRAFT"}),
                ),
            )

        result = await dispatch_service.record_attempt(
            request,
            status="FAILED",
            error={"reason": "integration test; no message was sent"},
        )
        dispatch_id = result.dispatch_id
        assert result.plan_id == plan_id
        assert result.status == "FAILED"
        print("PASS: dispatch attempt persisted.")

        duplicate = await dispatch_service.record_attempt(
            request,
            status="FAILED",
            error={"reason": "integration test retry"},
        )
        assert duplicate.dispatch_id == result.dispatch_id
        print("PASS: repeated idempotency key did not create a duplicate.")

        acknowledgement = DriverAcknowledgement(
            plan_id=plan_id,
            driver_id=driver_id,
            acknowledged=False,
            received_at=datetime.now(UTC),
            message="Integration test acknowledgement.",
        )
        await dispatch_service.record_acknowledgement(acknowledgement)

        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            cursor = await connection.execute(
                """
                SELECT payload FROM dispatches WHERE dispatch_id = %s
                """,
                (result.dispatch_id,),
            )
            row = await cursor.fetchone()

        payload = row[0] if row else None
        if isinstance(payload, str):
            payload = json.loads(payload)

        assert payload is not None
        assert payload["acknowledgement"]["acknowledged"] is False
        print("PASS: driver acknowledgement persisted.")

        event = AuditEvent(
            event_id=event_id,
            actor="integration_test",
            action="dispatch_test",
            entity_type="dispatch",
            entity_id=result.dispatch_id,
            outcome="FAILED",
            details={"test": True, "message_sent": False},
        )
        await audit_service.append(event)
        print("PASS: audit event persisted.")

        # Verify the audit event actually reached PostgreSQL.
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            cursor = await connection.execute(
                "SELECT event_id FROM audit_events WHERE event_id = %s",
                (event_id,),
            )
            assert await cursor.fetchone() is not None

        print("PASS: audit event retrieved from database.")

        # A duplicate event ID must not create another event.
        await audit_service.append(event)
        print("PASS: repeated audit event ID accepted idempotently.")

        # Verify non-existent plan/driver pairs do not receive acknowledgements.
        try:
            await dispatch_service.record_acknowledgement(
                DriverAcknowledgement(
                    plan_id=f"missing-{suffix}",
                    driver_id=driver_id,
                    acknowledged=True,
                )
            )
            raise AssertionError("Acknowledgement without a dispatch was accepted.")
        except ReliefRouteError as exc:
            assert exc.error.code == ErrorCode.NOT_FOUND

        print("PASS: acknowledgement without dispatch rejected.")

    finally:
        async with await psycopg.AsyncConnection.connect(
            database_url,
            connect_timeout=5,
        ) as connection:
            await connection.execute(
                "DELETE FROM audit_events WHERE event_id = %s",
                (event_id,),
            )
            await connection.execute(
                "DELETE FROM dispatches WHERE plan_id = %s",
                (plan_id,),
            )
            await connection.execute(
                "DELETE FROM plans WHERE plan_id = %s",
                (plan_id,),
            )

        print("Test records cleaned up.")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)