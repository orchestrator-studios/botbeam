import { useCallback, useEffect, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import type { LedgerBoard, LedgerSession } from '../types';

// The board obeys the Ledger Book's session cheat sheet (woodshed docs/ledger/):
// Rule 1 — it lists every session ever prompted, minus the ones you archived;
// Rule 2 — the glyph: solid green = processing, +⚡ = run, ring = waiting.
// Layout (rev 18–19): Active sessions are CARDS in a grid, in the server's
// stable order (first_seen asc — a card never moves while its session stays
// active; only glyphs update). Inactive (dormant) sessions list below, newest
// first. Beneath both, the EVENTS FEED — the record plane: recent events,
// newest first, each labeled with its stream. Statuses arrive stored/computed
// from the service; this view computes nothing and never re-sorts.

function relTime(iso: string | null): string {
  if (!iso) return '';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function Glyph({ s }: { s: LedgerSession }) {
  if (s.activity === 'waiting') return <span className="ledger-dot waiting" title="Waiting — your move" />;
  return (
    <span className="ledger-glyph" title={s.activity === 'run' ? 'Run — mutating right now' : 'Processing — Claude is working'}>
      <span className="ledger-dot processing" />
      {s.activity === 'run' && <span className="ledger-bolt">{'⚡'}</span>}
    </span>
  );
}

const COLLAPSE_KEY = 'botbeam.ledger.inactiveCollapsed';

export default function SessionsView() {
  const { ledgerBump } = useBotBeam();
  const [board, setBoard] = useState<LedgerBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  // Collapse state persists across reloads by ruling — a section that
  // re-expands on every refresh would be worse than no collapse at all.
  const [inactiveCollapsed, setInactiveCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === '1',
  );

  function toggleInactive() {
    setInactiveCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1');
      return !c;
    });
  }

  const load = useCallback(() => {
    botbeamApi.getLedgerBoard()
      .then((b) => { setBoard(b); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the board'));
  }, []);

  // Load on entry, refetch on every ledger WS event, and poll as a fallback
  // in case the socket is down.
  useEffect(() => { load(); }, [load, ledgerBump]);
  useEffect(() => {
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  async function archive(id: string) {
    try {
      await botbeamApi.archiveSession(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not archive');
    }
  }

  async function clearDormant() {
    setConfirmClear(false);
    try {
      await botbeamApi.archiveAllDormant();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not archive');
    }
  }

  const sessions = board?.sessions ?? [];
  // The server guarantees the order (active by first_seen asc, then inactive
  // by recency) — filter preserves it, so no client-side sorting.
  const active = sessions.filter((s) => s.status === 'active');
  const inactive = sessions.filter((s) => s.status !== 'active');
  // meta stays in the payload (it labels event pills) but isn't a working
  // stream, so it doesn't get a card.
  const streams = (board?.streams ?? []).filter((s) => s.id !== 'meta');

  return (
    <div className="main ledger-view">
      <div className="ledger-content">
        <div className="ledger-head">
          <h1>Sessions</h1>
          <p>
            Every session you ever prompted, minus the ones you archived. Active sessions hold
            their card — green is working, a ring is waiting on you. Exited sessions drop to the
            inactive list; archive what you're done with.
          </p>
          {inactive.length > 0 && (
            <button className="btn btn-ghost ledger-clear" onClick={() => setConfirmClear(true)}>
              Archive all inactive ({inactive.length})
            </button>
          )}
        </div>

        {error && <p className="form-error">{error}</p>}

        {board === null ? (
          <p className="ledger-empty">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="ledger-empty">No sessions on the board — prompt a Claude Code session and it appears here.</p>
        ) : (
          <>
            <section className="ledger-section">
              <h2>Active</h2>
              {active.length === 0 ? (
                <p className="ledger-empty">No active sessions.</p>
              ) : (
                <ul className="ledger-grid">
                  {active.map((s) => (
                    <li key={s.id} className="ledger-tile">
                      <div className="ledger-tile-top">
                        <Glyph s={s} />
                        <span className="ledger-when" title={s.last_event_at || ''}>{relTime(s.last_event_at)}</span>
                      </div>
                      <span className="ledger-label">{s.label || s.id.slice(0, 8)}</span>
                      <span className="ledger-meta">
                        {s.workspace_id || ''}{s.machine ? ` · ${s.machine}` : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {inactive.length > 0 && (
              <section className="ledger-section">
                <h2>
                  <button className="ledger-collapse" onClick={toggleInactive}
                    aria-expanded={!inactiveCollapsed}>
                    <span className={`ledger-chevron${inactiveCollapsed ? ' collapsed' : ''}`}>▾</span>
                    Inactive ({inactive.length})
                  </button>
                </h2>
                {!inactiveCollapsed && (
                <ul className="ledger-list">
                  {inactive.map((s) => (
                    <li key={s.id} className={`ledger-card ${s.status}`}>
                      <span className="ledger-dot dormant" title="Dormant — exited; resumable" />
                      <div className="ledger-card-main">
                        <span className="ledger-label">{s.label || s.id.slice(0, 8)}</span>
                        <span className="ledger-meta">
                          {s.workspace_id || ''}{s.machine ? ` · ${s.machine}` : ''}
                        </span>
                      </div>
                      <span className="ledger-when" title={s.last_event_at || ''}>{relTime(s.last_event_at)}</span>
                      <button className="ledger-archive" title="Archive — remove from the board (any activity brings it back)"
                        onClick={() => archive(s.id)}>
                        &times;
                      </button>
                    </li>
                  ))}
                </ul>
                )}
              </section>
            )}
          </>
        )}

        {board && (streams.length > 0 || board.events.length > 0) && (
          <div className="ledger-columns">
            <section className="ledger-section">
              <h2>Streams</h2>
              {streams.length === 0 ? (
                <p className="ledger-empty">No active streams.</p>
              ) : (
                <ul className="ledger-streams">
                  {streams.map((s) => (
                    <li key={s.id} className={`ledger-stream-card ${s.staleness || ''}`}>
                      <div className="ledger-stream-top">
                        <span className="ledger-label">{s.title || s.id}</span>
                        {(s.open_loops?.length ?? 0) > 0 && (
                          <span className="ledger-loops" title={s.open_loops.join('\n')}>
                            {s.open_loops.length} open
                          </span>
                        )}
                      </div>
                      {s.state && <span className="ledger-stream-state">{s.state}</span>}
                      {s.next_action && <span className="ledger-stream-next">→ {s.next_action}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="ledger-section">
              <h2>Events</h2>
              {board.events.length === 0 ? (
                <p className="ledger-empty">No events logged yet.</p>
              ) : (
                <ul className="ledger-feed">
                  {board.events.map((e) => (
                    <li key={e.id} className="ledger-feed-line" title={(e.body || []).join('\n')}>
                      <span className="ledger-feed-stream">{e.stream_id}</span>
                      <span className="ledger-feed-headline">{e.headline}</span>
                      <span className="ledger-when" title={e.at}>{relTime(e.at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}

        {board && (
          <p className="ledger-asof">
            as of {board.as_of ? new Date(board.as_of).toLocaleTimeString() : ''} · work products
            land in a later phase
          </p>
        )}
      </div>

      {confirmClear && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setConfirmClear(false); }}>
          <div className="modal">
            <h2>Archive all inactive sessions?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              Clears the inactive list off the board. Nothing is deleted — any session that does
              something comes right back.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setConfirmClear(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={clearDormant}>Archive all</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
