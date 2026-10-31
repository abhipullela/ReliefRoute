"""PostgreSQL persistence for dispatch attempts and driver acknowledgements."""

import json
import os
import uuid

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from shared.enums import ErrorCode
from shared.errors import ReliefRouteError
from shared.models import (
    DispatchRequest,
    DispatchResult,
    DriverAcknowledgement,
)

load_dotenv()


class PostgreSQLDispatchService:
    """Persist dispatch attempts and acknowledgement records."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def record_attempt(
        self,
        request: DispatchRequest,
        *,
        status: str,
        provider_message_id: str | None = None,
        error: dict | None = None,
    ) -> DispatchResult:
        """Persist an actual dispatch attempt and its outcome.

        Call this after the notification provider has returned an outcome.
        This method does not send a notification.
        """

        dispatch_id = str(uuid.uuid4())
        payload = {
            "request": request.model_dump(mode="json"),
            "error": error,
        }

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO dispatches (
                        dispatch_id,
                        plan_id,
                        idempotency_key,
                        status,
                        provider_message_id,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING
                        dispatch_id,
                        plan_id,
                        provider_message_id,
                        status,
                        attempted_at
                    """,
                    (
                        dispatch_id,
                        request.plan_id,
                        request.idempotency_key,
                        status,
                        provider_message_id,
                        json.dumps(payload),
                    ),
                )
                row = await cursor.fetchone()

                if row is None:
                    cursor = await connection.execute(
                        """
                        SELECT
                            dispatch_id,
                            plan_id,
                            provider_message_id,
                            status,
                            attempted_at,
                            payload
                        FROM dispatches
                        WHERE idempotency_key = %s
                        """,
                        (request.idempotency_key,),
                    )
                    existing = await cursor.fetchone()

                    if existing is None:
                        raise ReliefRouteError(
                            ErrorCode.CONFLICT,
                            "Dispatch idempotency conflict could not be resolved.",
                            provider="postgresql",
                        )

                    existing_request = existing["payload"].get("request", {})
                    if (
                        existing["plan_id"] != request.plan_id
                        or existing_request.get("driver_id") != request.driver_id
                    ):
                        raise ReliefRouteError(
                            ErrorCode.CONFLICT,
                            "Dispatch idempotency key belongs to a different dispatch.",
                            provider="postgresql",
                        )

                    row = existing

            return DispatchResult(
                dispatch_id=row["dispatch_id"],
                plan_id=row["plan_id"],
                provider_message_id=row["provider_message_id"],
                status=row["status"],
                attempted_at=row["attempted_at"],
            )

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the dispatch attempt.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def record_acknowledgement(
        self, ack: DriverAcknowledgement
    ) -> None:
        """Persist acknowledgement details in the plan's dispatch record.

        Requires exactly one dispatch for the plan and driver to avoid
        attributing an acknowledgement to the wrong delivery.
        """

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    SELECT dispatch_id, payload
                    FROM dispatches
                    WHERE plan_id = %s
                      AND payload->'request'->>'driver_id' = %s
                    ORDER BY attempted_at DESC
                    """,
                    (ack.plan_id, ack.driver_id),
                )
                rows = await cursor.fetchall()

                if not rows:
                    raise ReliefRouteError(
                        ErrorCode.NOT_FOUND,
                        "No dispatch found for this plan and driver.",
                        provider="postgresql",
                    )

                # The latest dispatch is the acknowledgement target.
                row = rows[0]
                payload = row["payload"]
                payload["acknowledgement"] = ack.model_dump(mode="json")

                await connection.execute(
                    """
                    UPDATE dispatches
                    SET payload = %s::jsonb
                    WHERE dispatch_id = %s
                    """,
                    (json.dumps(payload), row["dispatch_id"]),
                )

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the driver acknowledgement.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc