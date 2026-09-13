-- 004_ledger_record_plane.sql
-- Ledger Book rev 19, phase 2: the record plane — ledger_streams and
-- ledger_events. Both are NEW tables, so unlike 002/003 this migration is
-- OPTIONAL on an existing database: create_all at startup creates missing
-- tables (it just never ALTERs existing ones). It exists so the record of
-- schema changes stays complete and so the tables can be created ahead of a
-- deploy if desired. Safe to run repeatedly (IF NOT EXISTS).
--
-- The built-in `meta` stream is NOT seeded here: streams are per-user, and the
-- service creates each user's `meta` lazily on first reference — the same
-- pattern as the Default Org / default display.

CREATE TABLE IF NOT EXISTS ledger_streams (
  user_id       INT          NOT NULL,
  id            VARCHAR(64)  NOT NULL,
  title         VARCHAR(255) NULL,
  state         TEXT         NULL,
  next_action   TEXT         NULL,
  open_loops    JSON         NULL,
  working_paths JSON         NULL,
  since         DATETIME     NOT NULL,
  updated       DATETIME     NOT NULL,
  closed_at     DATETIME     NULL,
  PRIMARY KEY (user_id, id),
  CONSTRAINT fk_lstream_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ledger_events (
  id         VARCHAR(24)  NOT NULL,
  user_id    INT          NOT NULL,
  at         DATETIME     NOT NULL,
  stream_id  VARCHAR(64)  NOT NULL,
  headline   VARCHAR(500) NOT NULL,
  body       JSON         NOT NULL,
  session_id VARCHAR(36)  NULL,
  PRIMARY KEY (id),
  KEY ix_ledger_events_user_id (user_id),
  KEY ix_ledger_events_at (at),
  KEY ix_ledger_events_stream_id (stream_id),
  KEY ix_ledger_events_session_id (session_id),
  CONSTRAINT fk_levent_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  CONSTRAINT fk_levent_session FOREIGN KEY (session_id) REFERENCES ledger_sessions(id) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
