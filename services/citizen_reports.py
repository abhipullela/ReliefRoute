"""PostgreSQL storage for citizen-submitted incident reports."""

import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from shared.enums import ErrorCode, ReportTriageStatus
from shared.errors import ReliefRouteError
from shared.models import (
    CitizenReport,
    CitizenReportSubmission,
    CitizenReportTriage,
)

load_dotenv()


class PostgreSQLCitizenReportStore:
    """Persist reports and coordinate idempotent, recoverable AI triage."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "DATABASE_URL is not configured.",
                provider="postgresql",
            )

    async def create_or_get(self, submission: CitizenReportSubmission) -> CitizenReport:
        """Insert a report once or return the report for the same request key."""

        status = (
            ReportTriageStatus.PENDING
            if submission.ai_processing_consent
            else ReportTriageStatus.NOT_REQUESTED
        )
        now = datetime.now(UTC)
        report = CitizenReport(
            report_id=str(uuid4()),
            report_text=submission.report_text,
            location=submission.location,
            observed_at=submission.observed_at or now,
            created_at=now,
            updated_at=now,
            idempotency_key=submission.idempotency_key,
            ai_processing_consent=submission.ai_processing_consent,
            triage_status=status,
        )

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                cursor = await connection.execute(
                    """
                        INSERT INTO citizen_reports (
                            report_id, idempotency_key, triage_status, payload
                        )
                        VALUES (%s, %s, %s, %s::jsonb)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING payload
                        """,
                    (
                        report.report_id,
                        report.idempotency_key,
                        report.triage_status.value,
                        report.model_dump_json(),
                    ),
                )
                row = await cursor.fetchone()
                if row is not None:
                    return CitizenReport.model_validate(row["payload"])

                cursor = await connection.execute(
                    """
                        SELECT payload
                        FROM citizen_reports
                        WHERE idempotency_key = %s
                        FOR UPDATE
                        """,
                    (submission.idempotency_key,),
                )
                existing = await cursor.fetchone()
                if existing is None:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Citizen report idempotency conflict could not be resolved.",
                        provider="postgresql",
                    )

                saved = CitizenReport.model_validate(existing["payload"])
                if (
                    saved.report_text != submission.report_text
                    or saved.location != submission.location
                    or (
                        submission.observed_at is not None
                        and saved.observed_at != submission.observed_at
                    )
                    or saved.ai_processing_consent != submission.ai_processing_consent
                ):
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Report idempotency key belongs to a different submission.",
                        provider="citizen_reports",
                    )
                return saved

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not store the citizen report.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def claim_triage(self, report_id: str) -> tuple[CitizenReport, str] | None:
        """Claim a report for one worker, reclaiming a stale claim after five minutes."""

        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    """
                    UPDATE citizen_reports
                    SET triage_status = %s,
                        payload = jsonb_set(
                            jsonb_set(payload, '{triage_status}', to_jsonb(%s::text)),
                            '{triage_error}', 'null'::jsonb
                        ),
                        triage_claimed_at = NOW(),
                        triage_claim_token = %s,
                        updated_at = NOW()
                    WHERE report_id = %s
                      AND payload->>'ai_processing_consent' = 'true'
                      AND (
                        triage_status IN (%s, %s, %s)
                        OR (
                            triage_status = %s
                            AND triage_claimed_at < NOW() - INTERVAL '5 minutes'
                        )
                      )
                    RETURNING payload, triage_claim_token
                    """,
                    (
                        ReportTriageStatus.PROCESSING.value,
                        ReportTriageStatus.PROCESSING.value,
                        str(uuid4()),
                        report_id,
                        ReportTriageStatus.PENDING.value,
                        ReportTriageStatus.FAILED.value,
                        ReportTriageStatus.UNAVAILABLE.value,
                        ReportTriageStatus.PROCESSING.value,
                    ),
                )
                row = await cursor.fetchone()
            if row is None:
                return None
            return (
                CitizenReport.model_validate(row["payload"]),
                row["triage_claim_token"],
            )

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not claim citizen report triage.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def finish_triage(
        self,
        report_id: str,
        *,
        claim_token: str,
        status: ReportTriageStatus,
        triage: CitizenReportTriage | None = None,
        error: str | None = None,
    ) -> CitizenReport:
        """Store a triage result only while this worker owns the active claim."""

        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self.database_url,
                    row_factory=dict_row,
                    connect_timeout=5,
                ) as connection,
                connection.transaction(),
            ):
                cursor = await connection.execute(
                    """
                        SELECT payload
                        FROM citizen_reports
                        WHERE report_id = %s
                          AND triage_status = %s
                          AND triage_claim_token = %s
                        FOR UPDATE
                        """,
                    (
                        report_id,
                        ReportTriageStatus.PROCESSING.value,
                        claim_token,
                    ),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise ReliefRouteError(
                        ErrorCode.CONFLICT,
                        "Citizen report triage claim is no longer active.",
                        provider="citizen_reports",
                    )

                report = CitizenReport.model_validate(row["payload"])
                updated = report.model_copy(
                    update={
                        "triage_status": status,
                        "triage": triage,
                        "triage_error": error,
                        "updated_at": datetime.now(UTC),
                    }
                )
                cursor = await connection.execute(
                    """
                        UPDATE citizen_reports
                        SET triage_status = %s,
                            payload = %s::jsonb,
                            triage_claimed_at = NULL,
                        triage_claim_token = NULL,
                        updated_at = NOW()
                        WHERE report_id = %s
                          AND triage_claim_token = %s
                        RETURNING payload
                        """,
                    (
                        status.value,
                        json.dumps(updated.model_dump(mode="json")),
                        report_id,
                        claim_token,
                    ),
                )
                final_row = await cursor.fetchone()
            return CitizenReport.model_validate(final_row["payload"])

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not save citizen report triage.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def get_report(self, report_id: str) -> CitizenReport | None:
        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                cursor = await connection.execute(
                    "SELECT payload FROM citizen_reports WHERE report_id = %s",
                    (report_id,),
                )
                row = await cursor.fetchone()
            return CitizenReport.model_validate(row["payload"]) if row else None

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not retrieve the citizen report.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc

    async def list_reports(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        triage_status: ReportTriageStatus | None = None,
    ) -> list[CitizenReport]:
        if not 1 <= limit <= 100 or offset < 0:
            raise ReliefRouteError(
                ErrorCode.VALIDATION_ERROR,
                "limit must be between 1 and 100 and offset must be non-negative.",
                provider="citizen_reports",
            )
        try:
            async with await psycopg.AsyncConnection.connect(
                self.database_url,
                row_factory=dict_row,
                connect_timeout=5,
            ) as connection:
                if triage_status is None:
                    cursor = await connection.execute(
                        """
                        SELECT payload FROM citizen_reports
                        ORDER BY created_at DESC, report_id
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                else:
                    cursor = await connection.execute(
                        """
                        SELECT payload FROM citizen_reports
                        WHERE triage_status = %s
                        ORDER BY created_at DESC, report_id
                        LIMIT %s OFFSET %s
                        """,
                        (triage_status.value, limit, offset),
                    )
                rows = await cursor.fetchall()
            return [CitizenReport.model_validate(row["payload"]) for row in rows]

        except psycopg.Error as exc:
            raise ReliefRouteError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Could not list citizen reports.",
                retryable=True,
                provider="postgresql",
                details={"error_type": type(exc).__name__},
            ) from exc
