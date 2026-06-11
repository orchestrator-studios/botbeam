import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

// The lockbox panel: stashed entries (kind === 'lockbox') the user or their
// agent saved for later. Not rendered as tabs — clicking one opens it in the
// main view (reuses DeviceView via switchTab).
export default function LockboxPanel() {
  const { lockboxes, switchTab, activeTab } = useBotBeam();
  const [collapsed, setCollapsed] = useState(false);

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
            </div>
            {d.description && <div className="dropbox-item-meta">{d.description}</div>}
          </div>
        ))}
      </div>
    </aside>
  );
}
