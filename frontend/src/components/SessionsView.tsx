import { useCallback, useEffect, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import type { LedgerBoard, LedgerSession } from '../types';

// The board obeys the Ledger Book's session cheat sheet (woodshed docs/ledger/):
// Rule 1 — it lists every session ever prompted, minus archived, minus expired;
// Rule 2 — the glyph: solid green = processing, +⚡ = run, ring = waiting,
// gray = dormant (exited, crashed, or idle — unknowable and equivalent).
// Statuses arrive derived from the service; this view computes nothing.

function relTime(iso: string | null): string {
  if (!iso) return '';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function Glyph({ s }: { s: LedgerSession }) {
  if (s.status === 'dormant') return <span className="ledger-dot dormant" title="Dormant — silent; resumable" />;
  if (s.activity === 'waiting') return <span className="ledger-dot waiting" title="Waiting — your move" />;
  return (
    <span className="ledger-glyph" title={s.activity === 'run' ? 'Run — mutating right now' : 'Processing — Claude is working'}>
      <span className="ledger-dot processing" />
      {s.activity === 'run' && <span className="ledger-bolt">{'⚡'}</span>}
    </span>
  );
}

export default function SessionsView() {
  const { ledgerBump } = useBotBeam();
  const [board, setBoard] = useState<LedgerBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

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
  const dormantCount = sessions.filter((s) => s.status === 'dormant').length;

  return (
    <div className="main ledger-view">
      <div className="ledger-content">
        <div className="ledger-head">
          <h1>Sessions</h1>
          <p>
            Every session you ever prompted, minus the ones you archived, minus the ones whose
            transcript is gone. Green is working, a ring is waiting on you, gray is silent — archive
            what you're done with.
          </p>
          {dormantCount > 0 && (
            <button className="btn btn-ghost ledger-clear" onClick={() => setConfirmClear(true)}>
              Archive all dormant ({dormantCount})
            </button>
          )}
        </div>

        {error && <p className="form-error">{error}</p>}

        {board === null ? (
          <p className="ledger-empty">Loading…</p>
        ) : sessions.length === 0 ? (
          <p className="ledger-empty">No sessions on the board — prompt a Claude Code session and it appears here.</p>
        ) : (
          <ul className="ledger-list">
            {sessions.map((s) => (
              <li key={s.id} className={`ledger-card ${s.status}`}>
                <Glyph s={s} />
                <div className="ledger-card-main">
                  <span className="ledger-label">{s.label || s.id.slice(0, 8)}</span>
                  <span className="ledger-meta">
                    {s.workspace_id || ''}{s.machine ? ` · ${s.machine}` : ''}
                  </span>
                </div>
                <span className="ledger-when" title={s.last_event_at || ''}>{relTime(s.last_event_at)}</span>
                {s.status === 'dormant' && (
                  <button className="ledger-archive" title="Archive — remove from the board (any activity brings it back)"
                    onClick={() => archive(s.id)}>
                    &times;
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {board && (
          <p className="ledger-asof">
            as of {board.as_of ? new Date(board.as_of).toLocaleTimeString() : ''} · events and work
            products land here in phase 2
          </p>
        )}
      </div>

      {confirmClear && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setConfirmClear(false); }}>
          <div className="modal">
            <h2>Archive all dormant sessions?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              Clears every gray card off the board. Nothing is deleted — any session that does
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
