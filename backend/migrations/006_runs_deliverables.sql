-- 006_runs_deliverables.sql
-- Ledger Book rev 21: runs + deliverables land; the old computed ⚡ dies.
-- The bolt is no longer inferred from a decaying last_run_at inside a window
-- (invariant 2's last violation) — it is a declared Run with ended_at IS NULL.
-- last_run_at goes away with it; the two new tables are created by create_all
-- at startup (the CREATEs below exist for the record / optional pre-create).
--
-- ORDER INVERTED vs 002/003, same as 005: deploy the rev 21 code FIRST, then
-- run this. The old code SELECTs last_run_at via the ORM and would break the
-- moment it is dropped; the new code no longer maps it.

CREATE TABLE IF NOT EXISTS ledger_deliverables (
  id          VARCHAR(24)   NOT NULL,
  user_id     INT           NOT NULL,
  at          DATETIME      NOT NULL,
  name        VARCHAR(255)  NOT NULL,
  home        VARCHAR(1024) NOT NULL,
  state       TEXT          NULL,
  status      VARCHAR(16)   NOT NULL DEFAULT 'live',
  stream_id   VARCHAR(64)   NOT NULL,
  last_run_id VARCHAR(24)   NULL,
  updated     DATETIME      NOT NULL,
  PRIMARY KEY (id),
  KEY ix_ledger_deliverables_user_id (user_id),
  KEY ix_ledger_deliverables_stream_id (stream_id),
  CONSTRAINT fk_ldel_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ledger_runs (
  id             VARCHAR(24)  NOT NULL,
  user_id        INT          NOT NULL,
  deliverable_id VARCHAR(24)  NOT NULL,
  session_id     VARCHAR(36)  NOT NULL,
  intent         VARCHAR(500) NOT NULL,
  started_at     DATETIME     NOT NULL,
  ended_at       DATETIME     NULL,
  outcome        VARCHAR(16)  NULL,
  PRIMARY KEY (id),
  KEY ix_ledger_runs_user_id (user_id),
  KEY ix_ledger_runs_deliverable_id (deliverable_id),
  KEY ix_ledger_runs_session_id (session_id),
  CONSTRAINT fk_lrun_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  CONSTRAINT fk_lrun_deliverable FOREIGN KEY (deliverable_id) REFERENCES ledger_deliverables(id) ON DELETE CASCADE,
  CONSTRAINT fk_lrun_session FOREIGN KEY (session_id) REFERENCES ledger_sessions(id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE ledger_sessions DROP COLUMN last_run_at;
