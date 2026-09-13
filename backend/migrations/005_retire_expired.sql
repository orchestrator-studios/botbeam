-- 005_retire_expired.sql
-- Ledger Book rev 20: `expired` and the entire sweep apparatus are RETIRED.
-- Sessions are active | dormant | archived — three states, no fourth. An
-- expired session was, in truth, a dormant one whose transcript aged out of
-- Claude Code's own retention clock (cleanupPeriodDays) — a fact about a file
-- on one machine's disk, never a state of the session. The two observation
-- columns go with it, as does POST /ledger/sessions/sweep-report.
--
-- ORDER INVERTED vs 002/003: deploy the rev 20 code FIRST, then run this.
-- The new code no longer maps these columns (extra columns are harmless to
-- it), but the old code SELECTs them via the ORM and would break the moment
-- they are dropped. Deploy, then drop.

UPDATE ledger_sessions SET status = 'dormant' WHERE status = 'expired';

ALTER TABLE ledger_sessions
  DROP COLUMN transcript_missing_since,
  DROP COLUMN sweep_miss_count;
