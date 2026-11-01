# 11 — Testing and Acceptance

## Commands
```bash
python -m pip install -e '.[dev,agent,telegram,db]'
pytest
ruff check .
uvicorn api.main:app --reload
```

## Test layers
- Unit: validation, hazard threshold logic, idempotency, state transitions.
- Contract: services return shared models and expected errors.
- Integration: real provider smoke tests, opt-in via environment variables; don't make normal unit tests depend on internet.
- End-to-end: supplier registration -> inventory update -> driver GPS -> plan -> approval -> dispatch -> acknowledgement -> audit event.

## Required acceptance checklist
- [ ] Clean clone can install and run `/health`.
- [ ] Forecast comes from a live provider and shows timestamp/source.
- [ ] Supplier and inventory are genuinely registered, with update time.
- [ ] Driver location comes from a real device and is consented.
- [ ] Coordinate ordering is correct on map and routing requests.
- [ ] Candidate route warnings and limitations are visible.
- [ ] Dispatch before approval is rejected.
- [ ] Duplicate dispatch request is idempotent.
- [ ] Concurrent approval and dispatch requests cannot duplicate state transitions or sends.
- [ ] Telegram rejection, timeout, and malformed responses do not falsely report successful delivery.
- [ ] Citizen reports persist with idempotent submissions and consent-gated AI triage.
- [ ] AI failures remain explicit; AI classifications always require human review.
- [ ] Telegram message sent is not confused with acknowledgement.
- [ ] Missing/failed provider results in explicit degraded state.
- [ ] No credentials or personal data are committed.
- [ ] Audit events show the full operation.

## Test honesty
Mock provider responses are permitted in unit tests. They must not be represented as live demo observations. If a real provider cannot be reached, explicitly show the integration as unavailable.
