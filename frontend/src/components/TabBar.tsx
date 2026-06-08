import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

export default function TabBar() {
  const { devices, activeTab, switchTab, removeDevice, resetDevices, addDevice, connected, pulsingTab, version } = useBotBeam();
  const [showModal, setShowModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [showReset, setShowReset] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [newName, setNewName] = useState('');

  function handleAbout() {
    setShowAbout(true);
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    await addDevice(name);
    setShowModal(false);
    setNewName('');
  }

  function handleDelete(id: string) {
    setDeleteTarget(null);
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

        <button
          className={`tab ${activeTab === 'home' ? 'active' : ''}`}
          onClick={() => switchTab('home')}
        >
          Home
        </button>

        {devices.filter(d => !d.pickupMode).map(d => (
          <button
            key={d.id}
            className={`tab ${activeTab === d.id ? 'active' : ''} ${pulsingTab === d.id ? 'tab-pulse' : ''}`}
            onClick={() => switchTab(d.id)}
          >
            <span>{d.name}</span>
            <span
              className="tab-close"
              title="Delete tab"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget({ id: d.id, name: d.name });
              }}
            >
              &times;
            </span>
          </button>
        ))}

        <button className="tab tab-add" onClick={() => setShowModal(true)}>+</button>
        {devices.filter(d => !d.pickupMode).length > 0 && (
          <button className="tab tab-reset" title="Reset all tabs" onClick={() => setShowReset(true)}>
            Reset
          </button>
        )}
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
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setShowModal(false)}>Cancel</button>
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
              This will delete all tabs and their content. This can't be undone.
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

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setDeleteTarget(null); }}>
          <div className="modal">
            <h2>Delete "{deleteTarget.name}"?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              This will remove the tab and its content. This can't be undone.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => handleDelete(deleteTarget.id)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
