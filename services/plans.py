"""PostgreSQL persistence for delivery plans."""

import json
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from shared.enums import ErrorCode, PlanStatus
from shared.errors import ReliefRouteError
from shared.models import DeliveryPlan

load_dotenv()


class PostgreSQLPlanningStore:
    """Persist delivery plans with idempotency protection."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def save_plan(self, plan: DeliveryPlan) -> DeliveryPlan:
        """Insert a plan, or return the existing plan for the same idempotency key."""

        payload = plan.model_dump(mode="json")
        payload_json = json.dumps(payload)

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    INSERT INTO plans (
                        plan_id, status, idempotency_key, payload
                    )
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING payload
                    """,
                    (
                        plan.plan_id,
                        plan.status.value,
                        plan.idempotency_key,
                        payload_json,
                    ),
                )
                row = await cursor.fetchone()

                if row is not None:
                    return DeliveryPlan.model_validate(row["payload"])

                cursor = await connection.execute(
                    """
                    SELECT plan_id, payload
                    FROM plans
                    WHERE idempotency_key = %s
                    """,
                    (plan.idempotency_key,),
                )
                existing = await cursor.fetchone()

                if existing is None:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Plan idempotency conflict could not be resolved.",
                        provider="postgresql",
                    )

                if existing["plan_id"] != plan.plan_id:
                    # The key already belongs to a different plan. Do not
                    # silently treat that as a successful retry.
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Idempotency key already belongs to another plan.",
                        provider="postgresql",
                    )

                return DeliveryPlan.model_validate(existing["payload"])

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not persist the delivery plan.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def get_plan(self, plan_id: str) -> DeliveryPlan | None:
        """Retrieve a persisted plan by its identifier."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    "SELECT payload FROM plans WHERE plan_id = %s",
                    (plan_id,),
                )
                row = await cursor.fetchone()

            if row is None:
                return None

            return DeliveryPlan.model_validate(row["payload"])

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not retrieve the delivery plan.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def list_plans(self, limit: int = 50) -> list[DeliveryPlan]:
        """Retrieve recent plans ordered by creation time."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    "SELECT payload FROM plans ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = await cursor.fetchall()

            return [DeliveryPlan.model_validate(r["payload"]) for r in rows]

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not retrieve delivery plans.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def update_status(
        self, plan_id: str, status: PlanStatus
    ) -> DeliveryPlan:
        """Update status in both the indexed column and JSON payload."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    UPDATE plans
                    SET status = %s,
                        payload = jsonb_set(
                            payload, '{status}', to_jsonb(%s::text)
                        ),
                        updated_at = NOW()
                    WHERE plan_id = %s
                    RETURNING payload
                    """,
                    (status.value, status.value, plan_id),
                )
                row = await cursor.fetchone()

            if row is None:
                raise ReliefRouteError(
                    ErrorCode.NOT_FOUND,
                    f"Delivery plan '{plan_id}' was not found.",
                    provider="postgresql",
                )

            return DeliveryPlan.model_validate(row["payload"])

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not update the delivery plan status.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def transition_status(
        self,
        plan_id: str,
        status: PlanStatus,
        *,
        expected_statuses: tuple[PlanStatus, ...],
    ) -> DeliveryPlan | None:
        """Atomically transition a plan only when it is in an expected state."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    UPDATE plans
                    SET status = %s,
                        payload = jsonb_set(
                            payload, '{status}', to_jsonb(%s::text)
                        ),
                        updated_at = NOW()
                    WHERE plan_id = %s
                      AND status = ANY(%s)
                    RETURNING payload
                    """,
                    (
                        status.value,
                        status.value,
                        plan_id,
                        [value.value for value in expected_statuses],
                    ),
                )
                row = await cursor.fetchone()

            return DeliveryPlan.model_validate(row["payload"]) if row else None

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not transition the delivery plan status.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc