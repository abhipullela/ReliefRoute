# ADR-001: Initial Architecture

- Status: Accepted for hackathon v1
- Decision date: 2026-10-31
- Decision owners: all three team members

## Context
Three developers need to integrate independently before an end-of-day deadline. Uncoordinated data models and provider integrations are the main delivery risk.

## Decision
Use a modular Python backend with canonical Pydantic models and Protocol interfaces under `shared/`. FastAPI is the API boundary. PostgreSQL is the intended persistence layer. Provider calls live only under `services/`. Agent orchestration lives under `agent/`. The frontend and Telegram bot use API/contracts rather than direct DB access. All dispatches require human approval in v1.

## Consequences
Positive: shared types, testable boundaries, clear ownership, reduced merge conflicts.
Negative: contract design adds upfront work; some planned integrations may be deferred.
Mitigation: implement a thin vertical slice first and keep optional integrations explicitly optional.
