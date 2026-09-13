-- 007_emitter_kind.sql
-- Ledger Book invariant 11: every event names its emitter, and an emitter is
-- a place — a session, or the BotBeam board. The board is not the absence of
-- a session: encoding the newest concept in the model as a missing value was
-- explicitly rejected, so the place gets its own column and a backfill.
--
-- ledger_events gains emitter_kind ('session' | 'board'), NOT NULL;
-- session_id becomes nullable (a board event carries none). The pairing is
-- enforced as a CHECK, not a convention. Backfill: every existing row was
-- session-emitted, true of all of them at migration time.
--
-- ORDER (normal, unlike 005/006): run this BEFORE deploying the invariant-11
-- code. Old code never sets emitter_kind (the DEFAULT covers its inserts)
-- and always sets session_id, so it runs unchanged against the new schema;
-- new code fails hard without the column.

ALTER TABLE ledger_events
  ADD COLUMN emitter_kind VARCHAR(16) NOT NULL DEFAULT 'session' AFTER body,
  MODIFY COLUMN session_id VARCHAR(36) NULL;

UPDATE ledger_events SET emitter_kind = 'session';

ALTER TABLE ledger_events
  ADD CONSTRAINT ck_ledger_events_emitter_place CHECK (
    (emitter_kind = 'session' AND session_id IS NOT NULL)
    OR (emitter_kind = 'board' AND session_id IS NULL));
