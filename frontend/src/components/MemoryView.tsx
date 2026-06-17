import { useCallback, useEffect, useState } from 'react';
import { botbeamApi } from '../lib/api/botbeamApi';
import type { Memory, MemorySummary, MemoryCategory } from '../types';

const CATEGORIES: MemoryCategory[] = ['user', 'project', 'reference', 'feedback', 'note'];

export default function MemoryView() {
  const [items, setItems] = useState<MemorySummary[]>([]);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Record<string, Memory>>({});
  const [deleteTarget, setDeleteTarget] = useState<MemorySummary | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    botbeamApi
      .getMemories(q.trim() || undefined, category || undefined)
      .then((m) => { setItems(m); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load memories'))
      .finally(() => setLoading(false));
  }, [q, category]);

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  async function toggle(key: string) {
    if (expanded === key) { setExpanded(null); return; }
    setExpanded(key);
    if (!bodies[key]) {
      try {
        const full = await botbeamApi.getMemory(key);
        setBodies((b) => ({ ...b, [key]: full }));
      } catch { /* leave the body unloaded; the row still collapses/expands */ }
    }
  }

  async function remove(key: string) {
    setDeleteTarget(null);
    await botbeamApi.deleteMemory(key);
    setBodies((b) => { const next = { ...b }; delete next[key]; return next; });
    if (expanded === key) setExpanded(null);
    load();
  }

  return (
    <div className="main memory-view">
      <div className="memory-content">
        <div className="memory-head">
          <h1>Memory</h1>
          <p>Durable facts your agent remembers and recalls. Review them here, and prune what's stale.</p>
        </div>

        <div className="memory-controls">
          <input
            className="memory-search"
            type="search"
            placeholder="Search keys, descriptions, and bodies…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select className="memory-filter" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {error && <p className="form-error">{error}</p>}

        {loading && items.length === 0 ? (
          <p className="memory-empty">Loading…</p>
        ) : items.length === 0 ? (
          <p className="memory-empty">
            {q || category
              ? 'No memories match that filter.'
              : 'No memories yet — your agent will add them as it learns.'}
          </p>
        ) : (
          <ul className="memory-list">
            {items.map((m) => (
              <li key={m.key} className={`memory-card ${expanded === m.key ? 'open' : ''}`}>
                <div className="memory-card-head" onClick={() => toggle(m.key)}>
                  <span className={`memory-cat memory-cat-${m.category}`}>{m.category}</span>
                  <span className="memory-key">{m.key}</span>
                  {m.description && <span className="memory-desc">{m.description}</span>}
                  <span className="memory-when">
                    {m.updatedAt ? new Date(m.updatedAt).toLocaleDateString() : ''}
                  </span>
                  <button
                    className="memory-del"
                    title="Delete this memory"
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(m); }}
                  >
                    &times;
                  </button>
                </div>
                {expanded === m.key && (
                  <div className="memory-body">
                    {bodies[m.key]
                      ? <pre>{bodies[m.key].body}</pre>
                      : <p className="memory-empty">Loading…</p>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {deleteTarget && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setDeleteTarget(null); }}>
          <div className="modal">
            <h2>Delete memory "{deleteTarget.key}"?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              This removes the fact for good — your agent won't recall it again. This can't be undone.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => remove(deleteTarget.key)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
