# 12 — End-of-Day Demo Runbook

## Priority order
P0: API starts, live weather request, supplier/inventory registration, real driver location, plan/approval/dispatch/acknowledgement records, clear audit trail.
P1: route provider and mapped hazard avoidance.
P2: Agmarknet and satellite flood layers.
P3: polished UI and optional LLM narration.

## Suggested timeboxes (adjust to remaining hours)
- First 20 minutes: freeze contracts, verify keys, assign owners, run baseline tests.
- Next 60–90 minutes: each owner implements their smallest vertical-slice contribution.
- Midpoint: integrate weather -> hazard assessment -> route -> plan, even if UI is basic.
- Next block: approval -> dispatch -> acknowledgement.
- Final 60 minutes: feature freeze; test clean start and rehearse.
- Last 20 minutes: no new features; only fix demo blockers.

## Demo sequence
1. Show live forecast and its source/retrieval time.
2. Show a registered supplier and supplier-reported stock with last update.
3. Show real driver location and timestamp.
4. Generate a candidate route and explain hazard source/limitations.
5. Show `NEEDS_APPROVAL`; attempt dispatch before approval and demonstrate it is blocked.
6. Approve as operator; send driver instruction.
7. Show driver acknowledgement from the real Telegram account.
8. Show audit trail and one controlled failure (e.g. provider unavailable or stale GPS) with visible recovery.

## Demo safety
Use a controlled test delivery and consenting teammates. Do not dispatch real emergency vehicles or represent the prototype as an official safety system. Do not fabricate live data if an API fails.
