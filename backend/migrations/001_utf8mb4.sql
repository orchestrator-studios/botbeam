-- 001_utf8mb4.sql
-- Convert the BotBeam database from latin1 → utf8mb4 so rich text
-- (emoji, CJK, symbols, any language) stores losslessly.
--
-- Context: tables were auto-created (create_all) and inherited the database's
-- latin1 default, so content_body could not hold 4-byte UTF-8 (MySQL/MariaDB
-- error 1366). Existing data is ASCII, so CONVERT TO is lossless here.
--
-- Run once against the live database. Fresh installs no longer need this —
-- models.py now declares utf8mb4 per table.
--
-- Server: MariaDB 10.6.x   Collation: utf8mb4_unicode_ci

-- New tables created later default to utf8mb4 instead of latin1.
ALTER DATABASE botbeam
  CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;

-- Convert existing tables (rewrites every text column in one pass).
ALTER TABLE organizations CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE users         CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE devices       CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
