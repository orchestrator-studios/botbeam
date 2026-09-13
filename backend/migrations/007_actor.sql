-- 007_actor.sql
-- Ledger Book invariant 11: every write that records who acted names an
-- ACTOR — one prefixed identifier ("session:<id>", "board"), not a pair of
-- fields. The type is a property of the identifier itself; a reader never
-- reconstructs it from a relationship between columns.
--
-- ledger_events.actor VARCHAR(64) NOT NULL replaces session_id. Existing
-- rows rewrite to 'session:' || session_id — true of every row at migration
-- time. No nullable column, no CHECK, no enum. The FK to ledger_sessions
-- goes with the column (an actor is a typed identifier, not a join column);
-- user-scoped cascade via user_id remains.
--
-- ORDER: coordinated with the deploy, breaking window accepted (Cliff's
-- ruling: no legacy support, no dual-spelling period). Run this, deploy
-- immediately after. Old code fails on event writes/reads once session_id
-- is gone; new code fails until actor exists. Running sessions' skill
-- copies that still post session_id 422 until restarted — accepted.
--
-- NOTE: the DROP FOREIGN KEY name was verified against prod on 2026-09-13:
--   SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
--   WHERE TABLE_NAME='ledger_events' AND REFERENCED_TABLE_NAME='ledger_sessions';
--   -> ledger_events_ibfk_2

ALTER TABLE ledger_events
  ADD COLUMN actor VARCHAR(64) NOT NULL DEFAULT '' AFTER body;

UPDATE ledger_events SET actor = CONCAT('session:', session_id);

ALTER TABLE ledger_events DROP FOREIGN KEY ledger_events_ibfk_2;

ALTER TABLE ledger_events
  DROP COLUMN session_id,
  MODIFY COLUMN actor VARCHAR(64) NOT NULL,
  ADD INDEX ix_ledger_events_actor (actor);
