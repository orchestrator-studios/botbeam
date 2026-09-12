-- 003_ledger_status.sql
-- Ledger Book rev 18: the session lifecycle status (active|dormant|archived|
-- expired) becomes a STORED column with one writer per transition — hooks write
-- active/dormant, archive/unarchive write archived/dormant, the sweep writes
-- expired. All read-time derivation (including the silence-TTL rule) is deleted
-- from the code; this backfill applies that old derivation ONE last time, with
-- the shipped defaults (silence window 15 min, expiry at 3 sweep misses), so
-- existing rows land where the derivation would have put them.
--
-- Run once against the live database before deploying the code that reads it
-- (create_all only creates missing tables, never adds columns). Fresh installs
-- don't need this — models.py declares the column.

ALTER TABLE ledger_sessions
  ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'active';

-- Backfill = the retired derivation cascade, first match wins. Timestamps in
-- this table are naive UTC, hence UTC_TIMESTAMP().
UPDATE ledger_sessions SET status = CASE
  WHEN archived_at IS NOT NULL AND last_event_at <= archived_at THEN 'archived'
  WHEN sweep_miss_count >= 3 AND transcript_missing_since IS NOT NULL
       AND last_event_at <= transcript_missing_since THEN 'expired'
  WHEN (ended_at IS NOT NULL AND last_event_at <= ended_at)
       OR last_event_at <= UTC_TIMESTAMP() - INTERVAL 15 MINUTE THEN 'dormant'
  ELSE 'active'
END;
