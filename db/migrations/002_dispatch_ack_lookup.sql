CREATE INDEX IF NOT EXISTS dispatches_plan_driver_sent_idx
    ON dispatches (
        plan_id,
        (payload -> 'request' ->> 'driver_id'),
        attempted_at DESC
    )
    WHERE status = 'SENT';
