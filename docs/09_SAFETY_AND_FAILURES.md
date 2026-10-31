# 09 — Safety, Approval and Failure Policy

## Approval gate
For the hackathon demo, all dispatches require explicit human approval. Store approver ID, timestamp and decision. No agent or model may self-approve. Rejection terminates dispatch for that plan.

## Route language
Allowed: “candidate route avoids the mapped hazard polygon according to provider response”; “risk remains uncertain”; “no route available from configured provider.”
Forbidden: “guaranteed safe”; “road is open” without a current authoritative road-status source.

## Block dispatch when
- Plan does not exist or is not approved.
- Supplier is inactive, stock is stale/expired/insufficient, or inventory source is not supplier-reported.
- Driver identity/contact cannot be resolved.
- Required origin/destination or route is missing.
- Hazard assessment or critical data is stale beyond configured policy.
- Route provider failed or the route response is invalid.
- Idempotency key conflicts with a different payload.

## Failure matrix
- Weather timeout: retry twice; then mark degraded and do not present old forecast as live.
- Routing timeout/rate limit: retry within provider limits; otherwise no dispatch for a route-dependent plan.
- Supplier unavailable: return no eligible supplier; do not invent a fallback.
- Telegram send failure: record FAILED; don't claim sent.
- Telegram send timeout: check stored idempotency/update state before retry to avoid duplicates.
- No driver acknowledgement: mark `SENT_UNACKNOWLEDGED`; notify operator and ask for manual follow-up.
- GPS stale: display last timestamp and stale flag; do not treat it as live.
- Agent crash: persist plan/action state so restart does not repeat a dispatch.
- Invalid polygon: reject or mark assessment unusable; never pass malformed geometry to routing.

## Audit requirements
Log actor, action, entity ID, time, outcome, source references and safe details for supplier updates, plan creation, approval/rejection, dispatch attempt, acknowledgement, replanning and provider errors. Never log API tokens or unnecessary personal data.
