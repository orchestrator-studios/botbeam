-- oneoff-2026-09-13-junk-events.sql — NOT a schema migration (unnumbered).
-- Operator cleanup, Cliff's call 2026-09-13: surgically delete the two junk
-- events that landed in `meta` during the v1.7.0 live verification — the
-- "test" probe and the shipping event logged alongside it. Events are
-- immutable through the API by design; this is the same below-the-API plane
-- that admin reset lives on, scoped to exactly two known rows.

DELETE FROM ledger_events
WHERE id IN ('ev_9b0b8dee5b394b46', 'ev_75110b494ea54484');
