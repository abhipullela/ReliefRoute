# 08 — Agent State Machine

## State sequence
`MONITOR -> ASSESS -> PLAN -> GUARDRAIL_CHECK -> NEEDS_APPROVAL -> DISPATCH -> VERIFY`

Possible branches:
- `MONITOR -> DEGRADED`: essential data provider unavailable after retries.
- `ASSESS -> NO_ACTION`: no relevant hazard signal; record why and keep monitoring.
- `PLAN -> NO_FEASIBLE_PLAN`: no fresh stock, no usable route, or required data absent.
- `GUARDRAIL_CHECK -> BLOCKED`: stale data, invalid geometry, route/provider warning, or authorization condition fails.
- `NEEDS_APPROVAL -> REJECTED`: operator rejects.
- `DISPATCH -> DISPATCH_FAILED`: dispatch provider fails.
- `VERIFY -> REPLAN`: ETA drift exceeds threshold, driver reports blocked route, or acknowledgement times out.
- `REPLAN -> PLAN`: only up to `MAX_REPLAN_ATTEMPTS`; then `FAILED_NEEDS_OPERATOR`.

## Node responsibilities
- `monitor`: fetch current weather, fresh inventory, latest driver location; attach source metadata.
- `assess`: create a hazard assessment; describe what is measured vs inferred.
- `plan`: choose eligible supplier and ask routing service for candidate route.
- `guardrail_check`: deterministic validation; never delegate authorization to LLM.
- `approval`: persist human decision and approver.
- `dispatch`: send one idempotent dispatch for approved plan only.
- `verify`: distinguish sent, acknowledged, in-transit, and completed.
- `replan`: refresh data and compute a new plan; preserve previous plan and audit history.

## LLM boundary
LLM may summarize sources, explain trade-offs, or rank already validated candidates. It must not invent stock, coordinates, closures, acknowledgements, approvals, or API results. Deterministic code enforces all state transitions and authorization.

## Retry policy
At most 3 total attempts per transient call (initial + 2 retries), then fail visibly. Do not retry invalid input/authentication errors. Use bounded timeouts. Never retry a dispatch blindly after an ambiguous timeout; query the idempotency key/status first.
