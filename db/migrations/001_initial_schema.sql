-- PostgreSQL v1 logical schema. Add migrations rather than editing a deployed schema silently.
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  contact_channel TEXT NOT NULL,
  contact_handle TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS inventory (
  inventory_id BIGSERIAL PRIMARY KEY,
  supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
  commodity TEXT NOT NULL,
  quantity DOUBLE PRECISION NOT NULL CHECK (quantity > 0),
  unit TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ,
  source TEXT NOT NULL DEFAULT 'supplier_reported'
);
CREATE INDEX IF NOT EXISTS inventory_supplier_commodity_idx ON inventory(supplier_id, commodity);
CREATE TABLE IF NOT EXISTS driver_locations (
  location_id BIGSERIAL PRIMARY KEY,
  driver_id TEXT NOT NULL,
  latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  observed_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  accuracy_m DOUBLE PRECISION,
  consented BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS driver_locations_latest_idx ON driver_locations(driver_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS plans (
  plan_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS dispatches (
  dispatch_id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(plan_id),
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  provider_message_id TEXT,
  payload JSONB NOT NULL,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS audit_events (
  event_id TEXT PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  outcome TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_refs JSONB NOT NULL DEFAULT '[]'::jsonb
);
