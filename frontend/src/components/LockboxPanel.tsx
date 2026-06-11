import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

// The lockbox panel: stashed entries (kind === 'lockbox') the user or their
// agent saved for later. Not rendered as tabs — clicking one opens it in the
// main view (reuses DeviceView via switchTab).
export default function LockboxPanel() {
  const { lockboxes, switchTab, activeTab, archiveDevice, removeDevice } = useBotBeam();
  const [collapsed, setCollapsed] = useState(false);
  const [closeTarget, setCloseTarget] = useState<{ id: string; name: string } | null>(null);

  function handleArchive(id: string) {
    setCloseTarget(null);
    archiveDevice(id);
  }

  function handleDelete(id: string) {
    setCloseTarget(null);
    removeDevice(id);
  }

  if (lockboxes.length === 0) return null;

  if (collapsed) {
    return (
      <div
        className="dropbox-sidebar-collapsed"
        onClick={() => setCollapsed(false)}
        title="Expand lockboxes"
      >
        <span className="dropbox-sidebar-icon">{'\u{1F512}'}</span>
        <span className="dropbox-sidebar-count">{lockboxes.length}</span>
      </div>
    );
  }

  return (
    <aside className="dropbox-sidebar">
      <div className="dropbox-sidebar-header">
        <span className="dropbox-sidebar-title">Lockboxes</span>
        <button className="dropbox-sidebar-collapse" onClick={() => setCollapsed(true)} title="Collapse">
          ›
        </button>
      </div>
      <div className="dropbox-section">
        {lockboxes.map(d => (
          <div
            key={d.id}
            className={`dropbox-item ${activeTab === d.id ? 'dropbox-item-active' : ''}`}
            onClick={() => switchTab(d.id)}
          >
            <div className="dropbox-item-header">
              <span className="dropbox-item-name">{d.name}</span>
              <button
                className="dropbox-item-delete"
                title="Archive or delete lockbox"
                onClick={(e) => {
                  e.stopPropagation();
                  setCloseTarget({ id: d.id, name: d.name });
                }}
              >
                &times;
              </button>
            </div>
            {d.description && <div className="dropbox-item-meta">{d.description}</div>}
          </div>
        ))}
      </div>

      {/* Archive / delete modal */}
      {closeTarget && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setCloseTarget(null); }}>
          <div className="modal">
            <h2>Close "{closeTarget.name}"?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              Archive keeps the lockbox and its content — browse and restore it from Home. Delete is permanent.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setCloseTarget(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => handleDelete(closeTarget.id)}>Delete</button>
              <button className="btn btn-primary" onClick={() => handleArchive(closeTarget.id)}>Archive</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
