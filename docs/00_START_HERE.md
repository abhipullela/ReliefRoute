# 00 — Start Here

## Read in this order
1. `00_START_HERE.md`
2. `01_PROJECT_SCOPE.md`
3. `02_ARCHITECTURE.md`
4. `03_TEAM_OWNERSHIP.md`
5. `04_GIT_AND_TEAM_WORKFLOW.md`
6. `05_INTERFACE_CONTRACTS.md`
7. `06_DATA_AND_DATABASE.md`
8. `07_API_SPEC.md`
9. `08_AGENT_STATE_MACHINE.md`
10. `09_SAFETY_AND_FAILURES.md`
11. `10_LIVE_SOURCES.md`
12. `11_TESTING_AND_ACCEPTANCE.md`
13. `12_EOD_DEMO_RUNBOOK.md`

## Source-of-truth rule
Shared Python models in `shared/models.py`, enums in `shared/enums.py`, SQL in `db/schema.sql`, and the contracts documented here define v1. Do not create competing models in `agent/`, `services/`, `api/`, `bot/`, or `web/`.

## Freeze the contract
At kickoff, all three members review and agree to the public signatures and model fields. Commit that baseline as `chore: freeze v1 integration contracts`. Any later change requires a PR, a docs update, a test update, and a message to all dependent owners.

## Deadline rule
Today EOD means scope control. Prioritize one reliable vertical slice and a graceful, explicit unavailable state for unverified providers. Do not attempt every integration if it risks breaking the end-to-end demo.
