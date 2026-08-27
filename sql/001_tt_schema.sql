-- Realization time-tracking schema for postgres_audit
-- Forward migration: apply once. See 001_tt_schema_rollback.sql for undo.
-- Timezone: all timestamptz stored UTC; render Europe/Sofia in clients/reports.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS tt;

-- Clients mirror Notion; Notion stays the editing surface, Postgres the truth for hours.
CREATE TABLE tt.client (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name           text NOT NULL,
  name_local     text,
  notion_page_id text UNIQUE,
  active         boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Every bookable thing: client engagements, internal projects, admin buckets.
CREATE TABLE tt.stream (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind             text NOT NULL
                   CHECK (kind IN ('client', 'internal', 'admin')),
  client_id        uuid REFERENCES tt.client(id),
  name             text NOT NULL,
  code             text UNIQUE NOT NULL,
  notion_page_id   text UNIQUE,
  fiscal_year      int,
  fee_amount       numeric(12,2),
  fee_currency     text NOT NULL DEFAULT 'EUR',
  billing_model    text NOT NULL DEFAULT 'fixed'
                   CHECK (billing_model IN ('fixed', 'tm')),
  budget_hours     numeric(8,2),
  billable_default boolean NOT NULL DEFAULT false,
  status           text NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'blocked', 'complete', 'archived')),
  started_on       date,
  due_on           date,
  sort_hint        timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT client_streams_have_a_client
    CHECK ((kind = 'client') = (client_id IS NOT NULL)),
  CONSTRAINT only_client_streams_have_fees
    CHECK (kind = 'client' OR fee_amount IS NULL)
);

-- Immutable fact table. Corrections are new rows; never UPDATE a synced entry.
CREATE TABLE tt.time_entry (
  id             uuid PRIMARY KEY,
  device_id      text NOT NULL,
  activity       text NOT NULL,
  sub            text,
  stream_id      uuid REFERENCES tt.stream(id),
  task_notion_id text,
  person         text NOT NULL DEFAULT 'vz',
  billable       boolean NOT NULL DEFAULT false,
  started_at     timestamptz NOT NULL,
  ended_at       timestamptz NOT NULL,
  duration_s     int GENERATED ALWAYS AS
                   (EXTRACT(EPOCH FROM (ended_at - started_at))::int) STORED,
  note           text,
  source         text NOT NULL DEFAULT 'pwa'
                 CHECK (source IN ('pwa', 'shortcut', 'manual', 'backfill', 'import')),
  confidence     text NOT NULL DEFAULT 'timed'
                 CHECK (confidence IN ('timed', 'adjusted', 'reconstructed')),
  supersedes_id  uuid UNIQUE REFERENCES tt.time_entry(id),
  void           boolean NOT NULL DEFAULT false,
  reason         text,
  entered_at     timestamptz NOT NULL DEFAULT now(),
  synced_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sane_interval CHECK (ended_at > started_at),
  CONSTRAINT corrections_explain_themselves
    CHECK ((supersedes_id IS NULL AND NOT void) OR reason IS NOT NULL)
);

CREATE VIEW tt.entry_current AS
SELECT e.*
FROM tt.time_entry e
WHERE NOT EXISTS (
  SELECT 1 FROM tt.time_entry s WHERE s.supersedes_id = e.id
)
AND NOT e.void;

CREATE INDEX time_entry_stream_started_idx ON tt.time_entry (stream_id, started_at DESC);
CREATE INDEX time_entry_activity_started_idx ON tt.time_entry (activity, started_at DESC);
CREATE INDEX time_entry_started_idx ON tt.time_entry (started_at DESC);
CREATE INDEX time_entry_dirty_rollups_idx ON tt.time_entry (stream_id, entered_at DESC)
  WHERE supersedes_id IS NOT NULL OR void;

-- Target rates for future T&M engagements. Nothing reads this yet.
CREATE TABLE tt.rate (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stream_id     uuid NOT NULL REFERENCES tt.stream(id),
  target_hourly numeric(10,2) NOT NULL,
  valid_from    date NOT NULL,
  valid_to      date
);

-- Dirty periods for Notion Actual Hours re-roll-up (recompute, never increment).
CREATE TABLE tt.notion_dirty (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stream_id   uuid REFERENCES tt.stream(id),
  period_start date NOT NULL,
  period_end   date NOT NULL,
  marked_at   timestamptz NOT NULL DEFAULT now(),
  cleared_at  timestamptz
);

CREATE INDEX notion_dirty_open_idx ON tt.notion_dirty (stream_id)
  WHERE cleared_at IS NULL;

-- Realization: fixed-fee client streams only. Am I charging enough?
CREATE VIEW tt.realization AS
SELECT
  s.id,
  s.code,
  c.name AS client,
  c.name_local,
  s.name AS engagement,
  s.fee_amount,
  s.fee_currency,
  s.budget_hours,
  ROUND(COALESCE(SUM(t.duration_s), 0) / 3600.0, 2) AS hours,
  ROUND(
    COALESCE(SUM(t.duration_s), 0) / 3600.0 / NULLIF(s.budget_hours, 0) * 100,
    1
  ) AS burn_pct,
  ROUND(
    s.fee_amount / NULLIF(COALESCE(SUM(t.duration_s), 0) / 3600.0, 0),
    2
  ) AS effective_hourly,
  ROUND(
    100.0 * COALESCE(SUM(t.duration_s) FILTER (WHERE t.confidence <> 'timed'), 0)
      / NULLIF(SUM(t.duration_s), 0),
    1
  ) AS reconstructed_pct,
  s.status,
  s.fiscal_year
FROM tt.stream s
JOIN tt.client c ON c.id = s.client_id
LEFT JOIN tt.entry_current t ON t.stream_id = s.id
WHERE s.kind = 'client'
  AND s.billing_model = 'fixed'
GROUP BY s.id, c.name, c.name_local;

-- Utilization: all working time. How much of it reaches an invoice?
CREATE VIEW tt.utilization AS
SELECT
  date_trunc('month', t.started_at AT TIME ZONE 'Europe/Sofia') AS month,
  ROUND(SUM(t.duration_s) FILTER (WHERE t.billable) / 3600.0, 2) AS billable_h,
  ROUND(SUM(t.duration_s) FILTER (WHERE s.kind = 'internal') / 3600.0, 2) AS internal_h,
  ROUND(SUM(t.duration_s) FILTER (WHERE s.kind = 'admin') / 3600.0, 2) AS admin_h,
  ROUND(SUM(t.duration_s) / 3600.0, 2) AS total_h,
  ROUND(
    100.0 * SUM(t.duration_s) FILTER (WHERE t.billable)
      / NULLIF(SUM(t.duration_s), 0),
    1
  ) AS utilization_pct
FROM tt.entry_current t
LEFT JOIN tt.stream s ON s.id = t.stream_id
WHERE t.stream_id IS NOT NULL
GROUP BY 1
ORDER BY 1 DESC;

-- Helper: mark a stream's current month dirty when a correction lands.
CREATE OR REPLACE FUNCTION tt.mark_dirty_on_correction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  sid uuid;
  d0 date;
  d1 date;
BEGIN
  IF NEW.supersedes_id IS NULL AND NOT NEW.void THEN
    RETURN NEW;
  END IF;
  sid := NEW.stream_id;
  IF sid IS NULL AND NEW.supersedes_id IS NOT NULL THEN
    SELECT stream_id INTO sid FROM tt.time_entry WHERE id = NEW.supersedes_id;
  END IF;
  IF sid IS NULL THEN
    RETURN NEW;
  END IF;
  d0 := (NEW.started_at AT TIME ZONE 'Europe/Sofia')::date;
  d1 := (NEW.ended_at AT TIME ZONE 'Europe/Sofia')::date;
  INSERT INTO tt.notion_dirty (stream_id, period_start, period_end)
  VALUES (sid, d0, d1);
  RETURN NEW;
END;
$$;

CREATE TRIGGER time_entry_mark_dirty
  AFTER INSERT ON tt.time_entry
  FOR EACH ROW
  EXECUTE PROCEDURE tt.mark_dirty_on_correction();

COMMENT ON SCHEMA tt IS 'Realization time tracking — hours system of record for Easy Ventures';
COMMENT ON TABLE tt.time_entry IS 'Immutable. Corrections supersede; deletions void. Never UPDATE.';
COMMENT ON VIEW tt.entry_current IS 'Current truth = rows nothing supersedes, minus voids.';
COMMENT ON VIEW tt.realization IS 'Fixed-fee client engagements only. Effective hourly = fee / hours.';
COMMENT ON VIEW tt.utilization IS 'Billable share of working time (stream_id IS NOT NULL).';
