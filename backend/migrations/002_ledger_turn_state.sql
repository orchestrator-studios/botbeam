-- 002_ledger_turn_state.sql
-- Ledger Book rev 17: turn_state (waiting|processing) becomes a STORED status,
-- set explicitly by hook signals (UserPromptSubmit -> processing, Stop /
-- SessionEnd -> waiting) — never inferred from timestamps. The sweep repairs a
-- crashed session's stale 'processing' once the row derives dormant.
--
-- Run once against the live database before deploying the code that reads it
-- (create_all only creates missing tables, never adds columns). Fresh installs
-- don't need this — models.py declares the column.

ALTER TABLE ledger_sessions
  ADD COLUMN turn_state VARCHAR(16) NOT NULL DEFAULT 'waiting';
