CREATE TABLE IF NOT EXISTS citizen_reports (
  report_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  triage_status TEXT NOT NULL,
  payload JSONB NOT NULL,
  triage_claimed_at TIMESTAMPTZ,
  triage_claim_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS citizen_reports_created_idx
  ON citizen_reports (created_at DESC);

CREATE INDEX IF NOT EXISTS citizen_reports_triage_idx
  ON citizen_reports (triage_status, created_at DESC);
