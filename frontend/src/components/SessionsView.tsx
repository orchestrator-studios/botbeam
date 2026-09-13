import { useCallback, useEffect, useMemo, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import type { LedgerBoard, LedgerSession } from '../types';

// The board obeys the Ledger Book's session cheat sheet (woodshed docs/ledger/):
// Rule 1 — it lists every session ever prompted, minus the ones you archived;
// Rule 2 — the glyph: solid green = processing, +⚡ = run, ring = waiting.
// Layout (rev 18–21): Active sessions are CARDS in a grid, in the server's
// stable order (first_seen asc — a card never moves while its session stays
// active; only glyphs update). Inactive (dormant) sessions list below, newest
// first, collapsible. Beneath both, Streams | Deliverables side by side,
// then the Events feed full-width below the row.
//
// Visual language: each stream owns a color (hashed from its slug — stable
// per entity, never repainted when the set changes) shown on its card edge,
// on every event's and deliverable's stream pill, and as a dot on attributed
// session cards. Identity is never color-alone — the stream title always
// rides with the swatch. Events and deliverables carry their session as a
// chip (emitter / the one mid-run). No slug is special-cased: every stream gets
// a card, every event and deliverable gets a clickable pill. A pill must never
// point at a stream the board withholds, so nothing here is filtered by name.
// Statuses arrive stored/computed from the service; this view computes nothing
// and never re-sorts.

// Categorical palette (dataviz reference, dark column) — validated against
// this app's surface: 8/8 pass lightness band, chroma floor, CVD separation,
// normal-vision floor, and 3:1 contrast.
const STREAM_COLORS = [
  '#3987e5', '#d95926', '#199e70', '#c98500',
  '#d55181', '#008300', '#9085e9', '#e66767',
];

// djb2 — color follows the entity (stable across reloads and set changes;
// a collision at 9+ streams is tolerable because the title is always shown).
function streamColor(slug: string): string {
  let h = 5381;
  for (let i = 0; i < slug.length; i++) h = ((h << 5) + h + slug.charCodeAt(i)) >>> 0;
  return STREAM_COLORS[h % STREAM_COLORS.length];
}

function prettySlug(slug: string): string {
  return slug.replace(/-/g, ' ');
}

function relTime(iso: string | null): string {
  if (!iso) return '';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

// Two independent channels (rev 21): the circle answers "whose move is it"
// (turn_state), the bolt answers "is a deliverable being worked" (open_run).
// All four combinations are legal — ring+⚡ is work parked mid-run.
function Glyph({ s }: { s: LedgerSession }) {
  const circle = s.activity === 'waiting'
    ? <span className="ledger-dot waiting" title="Waiting — your move" />
    : <span className="ledger-dot processing" title="Processing — Claude is working" />;
  return (
    <span className="ledger-glyph">
      {circle}
      {s.open_run && (
        <span className="ledger-bolt"
          title={`Run open — ${s.open_run.intent}${s.open_run.deliverable_name ? ` · ${s.open_run.deliverable_name}` : ''}`}>
          {'⚡'}
        </span>
      )}
    </span>
  );
}

// "⚡ 6m · cutting rev 21" — elapsed ticks locally from started_at.
function fmtElapsed(startedAt: string): string {
  const secs = Math.max(0, (Date.now() - new Date(startedAt).getTime()) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h${Math.floor((secs % 3600) / 60)}m`;
}

// A stream's identity mark: color swatch + display name, everywhere the same.
function StreamTag({ slug, title, onClick }: { slug: string; title: string; onClick?: () => void }) {
  return (
    <span className="ledger-feed-stream" onClick={onClick} title={slug}>
      <span className="stream-dot" style={{ background: streamColor(slug) }} />
      {title}
    </span>
  );
}

// The emitting session, in the sessions' own visual language: a chip with a
// mini glyph when the session is on the board (live), muted id otherwise.
function SessionChip({ s, sid }: { s: LedgerSession | undefined; sid: string | null }) {
  if (!sid) return null;
  if (!s) return <span className="ledger-session-chip gone" title={sid}>{sid.slice(0, 6)}</span>;
  const dot = s.status !== 'active' ? 'dormant' : s.activity === 'waiting' ? 'waiting' : 'processing';
  return (
    <span className="ledger-session-chip" title={`${s.label || s.id} — ${s.status}`}>
      <span className={`ledger-dot mini ${dot}`} />
      {s.label || s.id.slice(0, 6)}
    </span>
  );
}

const COLLAPSE_KEY = 'botbeam.ledger.inactiveCollapsed';

export default function SessionsView() {
  const { ledgerBump } = useBotBeam();
  const [board, setBoard] = useState<LedgerBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  // Cross-highlight: hovering an event lights up its stream card and its
  // emitter's session card. Clicking a stream card filters the feed to it.
  const [hover, setHover] = useState<{ stream?: string | null; session?: string | null }>({});
  const [streamFilter, setStreamFilter] = useState<string | null>(null);
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
  // Every stream the server sends gets a card. No slug is special-cased here:
  // a stream the board references but refuses to show is a label pointing at a
  // place that doesn't exist, which is what the meta carve-out produced.
  const streams = board?.streams ?? [];

  const streamTitle = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of board?.streams ?? []) m[s.id] = s.title || prettySlug(s.id);
    return m;
  }, [board]);
  const sessionById = useMemo(() => {
    const m: Record<string, LedgerSession> = {};
    for (const s of sessions) m[s.id] = s;
    return m;
  }, [sessions]);

  const events = (board?.events ?? []).filter(
    (e) => !streamFilter || e.stream_id === streamFilter,
  );

  const deliverables = board?.deliverables ?? [];
  // deliverable_id → the session working it right now (its ⚡, joined
  // client-side from the sessions already on the board).
  const openRunByDeliverable = useMemo(() => {
    const m: Record<string, LedgerSession> = {};
    for (const s of sessions) {
      if (s.open_run) m[s.open_run.deliverable_id] = s;
    }
    return m;
  }, [sessions]);

  // The session card's stream dot — the third corner of the triangle.
  function streamDotFor(s: LedgerSession) {
    if (!s.stream_id) return null;
    return (
      <span className="stream-dot" title={streamTitle[s.stream_id] ?? prettySlug(s.stream_id)}
        style={{ background: streamColor(s.stream_id) }} />
    );
  }

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
                    <li key={s.id} className={`ledger-tile${hover.session === s.id ? ' hl' : ''}`}>
                      <div className="ledger-tile-top">
                        <Glyph s={s} />
                        <span className="ledger-tile-right">
                          {streamDotFor(s)}
                          <span className="ledger-when" title={s.last_event_at || ''}>{relTime(s.last_event_at)}</span>
                        </span>
                      </div>
                      <span className="ledger-label">{s.label || s.id.slice(0, 8)}</span>
                      <span className="ledger-meta">
                        {s.workspace_id || ''}{s.machine ? ` · ${s.machine}` : ''}
                      </span>
                      {s.open_run && (
                        <span className="ledger-run-line" title={s.open_run.deliverable_name || ''}>
                          ⚡ {fmtElapsed(s.open_run.started_at)} · {s.open_run.intent}
                        </span>
                      )}
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
                    <li key={s.id} className={`ledger-card ${s.status}${hover.session === s.id ? ' hl' : ''}`}>
                      <span className="ledger-dot dormant" title="Dormant — exited; resumable" />
                      {s.open_run && (
                        <span className="ledger-bolt dim"
                          title={`Leaked open run — ${s.open_run.intent} (close or abandon it)`}>
                          {'⚡'}
                        </span>
                      )}
                      <div className="ledger-card-main">
                        <span className="ledger-label">{s.label || s.id.slice(0, 8)}</span>
                        <span className="ledger-meta">
                          {s.workspace_id || ''}{s.machine ? ` · ${s.machine}` : ''}
                        </span>
                      </div>
                      {streamDotFor(s)}
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

        {board && (streams.length > 0 || deliverables.length > 0 || board.events.length > 0) && (
          <>
          <div className="ledger-columns">
            <section className="ledger-section">
              <h2>Streams</h2>
              {streams.length === 0 ? (
                <p className="ledger-empty">No active streams.</p>
              ) : (
                <ul className="ledger-streams">
                  {streams.map((s) => (
                    <li key={s.id}
                      className={`ledger-stream-card${hover.stream === s.id ? ' hl' : ''}${streamFilter === s.id ? ' selected' : ''}`}
                      style={{ borderLeftColor: streamColor(s.id) }}
                      onClick={() => setStreamFilter((f) => (f === s.id ? null : s.id))}
                      title={streamFilter === s.id ? 'Showing only this stream — click to clear' : 'Click to filter the feed to this stream'}>
                      <div className="ledger-stream-top">
                        <span className="ledger-label">{s.title || prettySlug(s.id)}</span>
                        <span className="ledger-stream-cues">
                          {s.staleness && s.staleness !== 'fresh' && (
                            <span className={`ledger-staleness ${s.staleness}`}>{s.staleness}</span>
                          )}
                          {(s.open_loops?.length ?? 0) > 0 && (
                            <span className="ledger-loops" title={s.open_loops.join('\n')}>
                              {s.open_loops.length} open
                            </span>
                          )}
                        </span>
                      </div>
                      {s.state && <span className="ledger-stream-state">{s.state}</span>}
                      {s.next_action && <span className="ledger-stream-next">→ {s.next_action}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="ledger-section">
              <h2>Deliverables</h2>
              {deliverables.length === 0 ? (
                <p className="ledger-empty">No deliverables yet — one is born with the run that needs it.</p>
              ) : (
                <ul className="ledger-streams">
                  {deliverables.map((d) => {
                    const worker = openRunByDeliverable[d.id];
                    return (
                      <li key={d.id}
                        className={`ledger-deliverable-card${hover.stream === d.stream_id ? ' hl' : ''}${streamFilter === d.stream_id ? ' selected' : ''}`}
                        style={{ borderLeftColor: streamColor(d.stream_id) }}
                        onMouseEnter={() => setHover({ stream: d.stream_id, session: worker?.id })}
                        onMouseLeave={() => setHover({})}>
                        <div className="ledger-stream-top">
                          <span className="ledger-label">{d.name}</span>
                          <span className="ledger-when" title={d.updated || ''}>{relTime(d.updated)}</span>
                        </div>
                        {d.state && <span className="ledger-stream-state">{d.state}</span>}
                        <div className="ledger-deliverable-links">
                          <StreamTag slug={d.stream_id}
                            title={streamTitle[d.stream_id] ?? prettySlug(d.stream_id)}
                            onClick={() => setStreamFilter((f) => (f === d.stream_id ? null : d.stream_id))} />
                          {worker?.open_run && (
                            <span className="ledger-run-line"
                              title={`${worker.label || worker.id} is working this now`}>
                              ⚡ {fmtElapsed(worker.open_run.started_at)} · {worker.open_run.intent}
                            </span>
                          )}
                          {worker && <SessionChip s={worker} sid={worker.id} />}
                        </div>
                        {d.home && <span className="ledger-deliverable-home">{d.home}</span>}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>

          <section className="ledger-section">
            <h2>
              Events
              {streamFilter && (
                <button className="ledger-filter-clear" onClick={() => setStreamFilter(null)}
                  title="Clear the stream filter">
                  <span className="stream-dot" style={{ background: streamColor(streamFilter) }} />
                  {streamTitle[streamFilter] ?? prettySlug(streamFilter)} &times;
                </button>
              )}
            </h2>
            {events.length === 0 ? (
              <p className="ledger-empty">
                {streamFilter ? 'No events in this stream.' : 'No events logged yet.'}
              </p>
            ) : (
              <ul className="ledger-feed">
                {events.map((e) => (
                  <li key={e.id}
                    className="ledger-feed-line"
                    title={(e.body || []).join('\n')}
                    onMouseEnter={() => setHover({ stream: e.stream_id, session: e.session_id })}
                    onMouseLeave={() => setHover({})}>
                    <StreamTag slug={e.stream_id}
                      title={streamTitle[e.stream_id] ?? prettySlug(e.stream_id)}
                      onClick={() => setStreamFilter((f) => (f === e.stream_id ? null : e.stream_id))} />
                    <span className="ledger-feed-headline">{e.headline}</span>
                    <SessionChip s={e.session_id ? sessionById[e.session_id] : undefined} sid={e.session_id} />
                    <span className="ledger-when" title={e.at}>{relTime(e.at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          </>
        )}

        {board && (
          <p className="ledger-asof">
            as of {board.as_of ? new Date(board.as_of).toLocaleTimeString() : ''}
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
