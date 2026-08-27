-- Rollback for 001_tt_schema.sql
-- Drops the entire tt schema and everything in it.
-- WARNING: destroys all time entries, streams, clients, rates, dirty markers.

DROP TRIGGER IF EXISTS time_entry_mark_dirty ON tt.time_entry;
DROP FUNCTION IF EXISTS tt.mark_dirty_on_correction();
DROP VIEW IF EXISTS tt.utilization;
DROP VIEW IF EXISTS tt.realization;
DROP TABLE IF EXISTS tt.notion_dirty;
DROP TABLE IF EXISTS tt.rate;
DROP TABLE IF EXISTS tt.time_entry;
DROP TABLE IF EXISTS tt.stream;
DROP TABLE IF EXISTS tt.client;
DROP SCHEMA IF EXISTS tt;

-- Note: pgcrypto extension is left in place (may be used elsewhere).
