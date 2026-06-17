import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

export default function TabBar() {
  const { displays, sharedDevices, activeTab, switchTab, removeDevice, archiveDevice, resetDevices, addDevice, pinDevice, connected, pulsingTab, version } = useBotBeam();
  const [showModal, setShowModal] = useState(false);
  const [closeTarget, setCloseTarget] = useState<{ id: string; name: string } | null>(null);
  const [showReset, setShowReset] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [newName, setNewName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  function handleAbout() {
    setShowAbout(true);
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    try {
      await addDevice(name);
      setShowModal(false);
      setNewName('');
      setCreateError(null);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Could not create the tab');
    }
  }

  function handleArchive(id: string) {
    setCloseTarget(null);
    archiveDevice(id);
  }

  function handleDelete(id: string) {
    setCloseTarget(null);
    removeDevice(id);
  }

  return (
    <>
      <nav className="tab-bar">
        <span className="back-group">
          <a className="back-link" href="/">
            <span className={`ws-dot ${connected ? 'on' : ''}`} title={connected ? 'Connected' : 'Disconnected'} />
            BotBeam
          </a>
          <button className="tab-about" title="About BotBeam" onClick={handleAbout}>v{version}</button>
        </span>

        {/* App navigation — chrome, deliberately NOT styled like the content tabs */}
        <button
          className={`nav-btn ${activeTab === 'home' ? 'active' : ''}`}
          onClick={() => switchTab('home')}
          title="Home"
        >
          <span className="nav-btn-icon">{'\u{1F3E0}'}</span>Home
        </button>

        {/* The content tab strip — displays are the only things that look like tabs.
            This is the one region that scrolls when it overflows. */}
        <div className="tab-strip">
          {displays.map(d => (
            <button
              key={d.id}
              className={`tab ${activeTab === d.id ? 'active' : ''} ${pulsingTab === d.id ? 'tab-pulse' : ''}`}
              onClick={() => switchTab(d.id)}
            >
              <span>{d.name}</span>
              <span
                className="tab-pin"
                title={`Pin this browser to "${d.name}" (kiosk mode)`}
                onClick={(e) => {
                  e.stopPropagation();
                  pinDevice(d.id);
                }}
              >
                {'\u{1F4CC}'}
              </span>
              {!d.isDefault && (
                <span
                  className="tab-close"
                  title="Archive or delete tab"
                  onClick={(e) => {
                    e.stopPropagation();
                    setCloseTarget({ id: d.id, name: d.name });
                  }}
                >
                  &times;
                </span>
              )}
            </button>
          ))}

          <button className="tab tab-add" onClick={() => setShowModal(true)} title="New display">+</button>
          {displays.some(d => !d.isDefault) && (
            <button className="tab tab-reset" title="Reset all tabs" onClick={() => setShowReset(true)}>
              Reset
            </button>
          )}

          {sharedDevices.length > 0 && <span className="tab-divider" title="Shared with me" />}
          {sharedDevices.map(d => (
            <button
              key={d.id}
              className={`tab tab-shared ${activeTab === d.id ? 'active' : ''} ${pulsingTab === d.id ? 'tab-pulse' : ''}`}
              onClick={() => switchTab(d.id)}
              title={d.ownerEmail ? `Shared by ${d.ownerEmail} (view-only)` : 'Shared with me (view-only)'}
            >
              <span className="tab-shared-icon">{'\u{1F465}'}</span>
              <span>{d.name}</span>
              <span
                className="tab-pin"
                title={`Pin this browser to "${d.name}" (kiosk mode)`}
                onClick={(e) => {
                  e.stopPropagation();
                  pinDevice(d.id);
                }}
              >
                {'\u{1F4CC}'}
              </span>
            </button>
          ))}
        </div>

        <button
          className={`nav-btn ${activeTab === 'memory' ? 'active' : ''}`}
          onClick={() => switchTab('memory')}
          title="Memory — durable facts your agent recalls"
        >
          <span className="nav-btn-icon">{'\u{1F9E0}'}</span>Memory
        </button>

        <button
          className={`nav-btn ${activeTab === 'help' ? 'active' : ''}`}
          onClick={() => switchTab('help')}
          title="Help & docs"
        >
          <span className="nav-btn-icon">{'\u{2753}'}</span>Help
        </button>
      </nav>

      {/* New device modal */}
      {showModal && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowModal(false); }}>
          <div className="modal">
            <h2>New Device</h2>
            <input
              type="text"
              placeholder="Device name (e.g. kitchen)"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleCreate(); }}
              autoFocus
            />
            {createError && <p className="form-error">{createError}</p>}
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => { setShowModal(false); setCreateError(null); }}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            </div>
          </div>
        </div>
      )}

      {/* Reset confirmation modal */}
      {showReset && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowReset(false); }}>
          <div className="modal">
            <h2>Reset all tabs?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              This deletes every tab — including archived ones. Your main display is kept, cleared. This can't be undone.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setShowReset(false)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => { resetDevices(); setShowReset(false); }}>Reset</button>
            </div>
          </div>
        </div>
      )}

      {/* About modal */}
      {showAbout && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setShowAbout(false); }}>
          <div className="modal" style={{ textAlign: 'center' }}>
            <h2>BotBeam</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 8px' }}>
              AI-Powered Virtual Display Platform
            </p>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Version {version}
            </p>
            <div className="actions" style={{ marginTop: '16px' }}>
              <button className="btn btn-primary" onClick={() => setShowAbout(false)}>OK</button>
            </div>
          </div>
        </div>
      )}

      {/* Archive / delete modal */}
      {closeTarget && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setCloseTarget(null); }}>
          <div className="modal">
            <h2>Close "{closeTarget.name}"?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              Archive keeps the tab and its content — browse and restore it from Home. Delete is permanent.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setCloseTarget(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => handleDelete(closeTarget.id)}>Delete</button>
              <button className="btn btn-primary" onClick={() => handleArchive(closeTarget.id)}>Archive</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
