"""Citizen-report intake and advisory GenAI triage orchestration."""

from uuid import NAMESPACE_URL, uuid5

from shared.enums import ErrorCode, ReportTriageStatus
from shared.errors import ReliefRouteError
from shared.models import (
    AuditEvent,
    CitizenReport,
    CitizenReportSubmission,
    CitizenReportTriage,
)


class CitizenReportAgent:
    """Persist citizen reports and run consent-gated, human-reviewed AI triage."""

    def __init__(self, *, store, triage_provider, audit=None) -> None:
        self.store = store
        self.triage_provider = triage_provider
        self.audit = audit

    async def submit(self, submission: CitizenReportSubmission) -> CitizenReport:
        report = await self.store.create_or_get(submission)
        if self.audit is not None:
            await self.audit.append(
                self._event(
                    report,
                    action="CITIZEN_REPORT_RECEIVED",
                    outcome="SUCCESS",
                    details={"triage_status": report.triage_status.value},
                    event_id_suffix="received",
                )
            )
        return await self.triage(report.report_id)

    async def triage(self, report_id: str) -> CitizenReport:
        """Claim and triage one report; retries are safe and never duplicate work."""

        report = await self.store.get_report(report_id)
        if report is None:
            raise ReliefRouteError(
                ErrorCode.NOT_FOUND,
                f"Citizen report '{report_id}' was not found.",
                provider="citizen_reports",
            )
        if not report.ai_processing_consent:
            return report

        claim = await self.store.claim_triage(report_id)
        if claim is None:
            current = await self.store.get_report(report_id)
            if current is None:
                raise ReliefRouteError(
                    ErrorCode.NOT_FOUND,
                    f"Citizen report '{report_id}' was not found.",
                    provider="citizen_reports",
                )
            return current

        claimed, claim_token = claim
        try:
            triage_result: CitizenReportTriage = await self.triage_provider.triage(claimed)
            triage_result = triage_result.model_copy(update={"needs_human_review": True})
            result = await self.store.finish_triage(
                report_id,
                claim_token=claim_token,
                status=ReportTriageStatus.COMPLETE,
                triage=triage_result,
            )
        except ReliefRouteError as exc:
            status = (
                ReportTriageStatus.UNAVAILABLE
                if exc.error.code
                in {
                    ErrorCode.UPSTREAM_TIMEOUT,
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    ErrorCode.UPSTREAM_RATE_LIMITED,
                }
                else ReportTriageStatus.FAILED
            )
            result = await self.store.finish_triage(
                report_id,
                claim_token=claim_token,
                status=status,
                error=exc.error.message,
            )
        except Exception:
            await self.store.finish_triage(
                report_id,
                claim_token=claim_token,
                status=ReportTriageStatus.FAILED,
                error="GenAI triage failed due to an internal error.",
            )
            raise

        if self.audit is not None:
            details = {"triage_status": result.triage_status.value}
            if result.triage is not None:
                details.update(
                    category=result.triage.category.value,
                    severity=result.triage.severity.value,
                )
            await self.audit.append(
                self._event(
                    result,
                    action="CITIZEN_REPORT_TRIAGED",
                    outcome=result.triage_status.value,
                    details=details,
                    event_id_suffix=(
                        result.triage.generated_at.isoformat()
                        if result.triage
                        else result.updated_at.isoformat()
                    ),
                )
            )
        return result

    @staticmethod
    def _event(
        report: CitizenReport,
        *,
        action: str,
        outcome: str,
        details: dict,
        event_id_suffix: str,
    ) -> AuditEvent:
        return AuditEvent(
            event_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"reliefroute:citizen-report:{report.report_id}:{action}:{event_id_suffix}",
                )
            ),
            actor="system",
            action=action,
            entity_type="citizen_report",
            entity_id=report.report_id,
            outcome=outcome,
            details=details,
        )
