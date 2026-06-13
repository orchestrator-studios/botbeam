import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import type { Device } from '../types';

interface Props {
  device: Device;
  onClose: () => void;
}

// Owner-only dialog to manage view-only access to a display. Grantees are added
// by the email of an existing BotBeam account; the current list comes from the
// device's `sharedWith` (kept fresh by shareDevice/unshareDevice).
export default function ShareModal({ device, onClose }: Props) {
  const { shareDevice, unshareDevice } = useBotBeam();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The live list lives on the device in context; this prop re-renders on update.
  const grantees = device.sharedWith ?? [];

  async function add() {
    const value = email.trim();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    try {
      await shareDevice(device.id, value);
      setEmail('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not share');
    } finally {
      setBusy(false);
    }
  }

  async function remove(grantee: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await unshareDevice(device.id, grantee);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revoke');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <h2>Share "{device.name}"</h2>
        <p style={{ color: 'var(--text-muted)', margin: '0 0 16px', fontSize: '0.85rem' }}>
          Enter the email someone signed up to BotBeam with — it identifies their account,
          it doesn't email them anything. They get a live, read-only view of this display
          under their "Shared with me."
        </p>

        <div className="share-add">
          <input
            type="email"
            placeholder="person@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') add(); }}
            autoFocus
          />
          <button className="btn btn-primary" onClick={add} disabled={busy || !email.trim()}>Add</button>
        </div>
        {error && <p className="form-error">{error}</p>}

        <div className="share-list">
          {grantees.length === 0 ? (
            <p className="share-empty">Not shared with anyone yet.</p>
          ) : (
            grantees.map((g) => (
              <div key={g} className="share-row">
                <span className="share-email">{g}</span>
                <button className="btn btn-ghost btn-sm" onClick={() => remove(g)} disabled={busy}>Remove</button>
              </div>
            ))
          )}
        </div>

        <div className="actions" style={{ marginTop: '16px' }}>
          <button className="btn btn-ghost" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
