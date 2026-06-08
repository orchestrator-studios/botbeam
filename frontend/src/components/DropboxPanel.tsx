import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import type { Device } from '../types';

export default function DropboxPanel() {
  const { devices, removeDevice, pulsingDropbox, switchTab, activeTab } = useBotBeam();
  const [collapsed, setCollapsed] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const dropboxes = devices.filter(d => !!d.pickupMode);

  if (dropboxes.length === 0) return null;

  const active = dropboxes.filter(d =>
    d.pickupMode === 'single' ? (d.pickupCount ?? 0) === 0 : true
  );
  const pickedUp = dropboxes.filter(d =>
    d.pickupMode === 'single' && (d.pickupCount ?? 0) > 0
  );

  function copyId(id: string) {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  }

  function handleDelete(id: string) {
    removeDevice(id);
    setDeleteTarget(null);
  }

  if (collapsed) {
    return (
      <div
        className={`dropbox-sidebar-collapsed ${pulsingDropbox ? 'dropbox-pulse' : ''}`}
        onClick={() => setCollapsed(false)}
        title="Expand dropboxes"
      >
        <span className="dropbox-sidebar-icon">{'\u{1F4E6}'}</span>
        <span className="dropbox-sidebar-count">{dropboxes.length}</span>
      </div>
    );
  }

  return (
    <>
      <aside className="dropbox-sidebar">
        <div className="dropbox-sidebar-header">
          <span className="dropbox-sidebar-title">Dropboxes</span>
          <button className="dropbox-sidebar-collapse" onClick={() => setCollapsed(true)} title="Collapse">
            ›
          </button>
        </div>

        {active.length > 0 && (
          <div className="dropbox-section">
            <div className="dropbox-section-label">Awaiting Pickup</div>
            {active.map(d => (
              <DropboxItem
                key={d.id}
                device={d}
                isActive={activeTab === d.id}
                isPulsing={pulsingDropbox === d.id}
                copiedId={copiedId}
                onCopyId={copyId}
                onView={() => switchTab(d.id)}
                onDelete={() => setDeleteTarget({ id: d.id, name: d.name })}
              />
            ))}
          </div>
        )}

        {pickedUp.length > 0 && (
          <div className="dropbox-section">
            <div className="dropbox-section-label">Picked Up</div>
            {pickedUp.map(d => (
              <DropboxItem
                key={d.id}
                device={d}
                isActive={activeTab === d.id}
                isPulsing={pulsingDropbox === d.id}
                copiedId={copiedId}
                onCopyId={copyId}
                onView={() => switchTab(d.id)}
                onDelete={() => setDeleteTarget({ id: d.id, name: d.name })}
                muted
              />
            ))}
          </div>
        )}
      </aside>

      {deleteTarget && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setDeleteTarget(null); }}>
          <div className="modal">
            <h2>Delete &ldquo;{deleteTarget.name}&rdquo;?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              This will permanently remove the dropbox and its data.
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

function DropboxItem({ device, isActive, isPulsing, copiedId, onCopyId, onView, onDelete, muted }: {
  device: Device;
  isActive: boolean;
  isPulsing: boolean;
  copiedId: string | null;
  onCopyId: (id: string) => void;
  onView: () => void;
  onDelete: () => void;
  muted?: boolean;
}) {
  const pickupCount = device.pickupCount ?? 0;

  return (
    <div className={`dropbox-item ${isActive ? 'dropbox-item-active' : ''} ${muted ? 'dropbox-item-muted' : ''} ${isPulsing ? 'dropbox-item-pulse' : ''}`} onClick={onView}>
      <div className="dropbox-item-header">
        <span className="dropbox-item-name">{device.name}</span>
        <button className="dropbox-item-delete" onClick={(e) => { e.stopPropagation(); onDelete(); }} title="Delete">&times;</button>
      </div>
      <div className="dropbox-item-id" onClick={(e) => { e.stopPropagation(); onCopyId(device.id); }} title="Click to copy ID">
        {copiedId === device.id ? 'Copied!' : device.id}
      </div>
      <div className="dropbox-item-meta">
        <span className={`dropbox-item-status ${muted ? 'picked-up' : ''}`}>
          {muted ? 'Picked up' : device.pickupMode === 'multi' ? 'Multi-use' : 'Single-use'}
        </span>
        {pickupCount > 0 && (
          <span className="dropbox-item-count">{pickupCount} pickup{pickupCount !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  );
}
