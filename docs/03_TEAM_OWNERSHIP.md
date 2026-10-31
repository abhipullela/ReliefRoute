# 03 — Three-Person Ownership

## Member A — Agent and guardrails
Owns: `agent/`, agent tests, state transitions, planning orchestration, bounded retries, approval enforcement and audit event generation.
Consumes: `shared/*`, service Protocols from `shared/contracts.py`.
Must not: write separate weather/routing clients, query provider APIs directly, bypass approval or invent missing data.
Done when: agent consumes typed service outputs, creates plans, blocks unauthorized dispatch, and replans or terminates safely on failure.

## Member B — Data, geospatial and backend
Owns: `services/`, `api/`, `db/`, provider integration tests and schema migrations.
Must: normalize upstream responses into shared models; record source and timestamps; validate coordinates; handle timeout/rate-limit/auth/invalid responses distinctly.
Must not: call mandi arrivals supplier inventory; label route safe; return fake success when API fails.
Done when: interfaces have tests, DB persists suppliers/inventory/locations/plans/dispatch/audit, `/health` works, and unavailable providers return typed errors.

## Member C — UI, Telegram, delivery and demo
Owns: `web/`, `bot/`, UI/bot tests, deployment, README/demo.
Must: consume API contracts only; display source freshness, status and warnings; separate sent vs acknowledged; expose approval/rejection.
Must not: access DB directly, fabricate GPS/inventory, dispatch before approval.
Done when: real supplier and driver inputs appear in UI/API, operator can approve/reject, driver can acknowledge, audit trail is visible.

## Shared ownership
All members review `shared/`, docs contracts and `db/schema.sql` changes. No one changes public fields/signatures unilaterally.
