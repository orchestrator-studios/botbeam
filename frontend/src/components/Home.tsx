import { useCallback, useEffect, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import { settings } from '../config/settings';
import { TYPE_META } from '../lib/contentMeta';
import type { Device } from '../types';
import DeviceCard from './DeviceCard';

export default function Home() {
  const { devices, switchTab, user, logout, unarchiveDevice } = useBotBeam();
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [archived, setArchived] = useState<Device[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);

  const loadArchive = useCallback(() => {
    botbeamApi.getArchivedDevices().then(setArchived).catch(() => {});
  }, []);

  // `devices` changes on every archive/unarchive WS event, so the archive
  // listing stays in sync with actions taken here, in the tab bar, or by the agent.
  useEffect(loadArchive, [loadArchive, devices]);

  async function restore(id: string) {
    await unarchiveDevice(id);
    loadArchive();
  }

  async function destroy(id: string) {
    setDeleteTarget(null);
    await botbeamApi.deleteDevice(id);
    loadArchive();
  }

  async function mint() {
    const t = await botbeamApi.createAgentToken();
    setNewToken(t.access_token);
  }

  function copy(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const credsSnippet = newToken
    ? JSON.stringify({ base_url: settings.publicUrl, token: newToken }, null, 2)
    : null;

  return (
    <div className="main home-view">
      <div className="home-content">
        <div className="home-account">
          <span>Signed in as <strong>{user}</strong></span>
          <button className="btn btn-ghost" onClick={logout}>Sign out</button>
        </div>

        {devices.length > 0 && (
          <div className="device-grid">
            {devices.map((d) => (
              <DeviceCard key={d.id} device={d} onClick={() => switchTab(d.id)} />
            ))}
          </div>
        )}

        {archived.length > 0 && (
          <div className="archive-panel">
            <h2>Archive</h2>
            <p>Tabs taken off the display, kept with their content. Restore puts one back.</p>
            {archived.map((d) => (
              <div key={d.id} className="archive-row">
                <span className="archive-name">{d.name}</span>
                <span className="archive-meta">
                  {d.content ? (TYPE_META[d.content.type]?.label ?? d.content.type) : 'empty'}
                  {d.archivedAt && ` · archived ${new Date(d.archivedAt).toLocaleDateString()}`}
                </span>
                <span className="archive-actions">
                  <button className="btn btn-primary" onClick={() => restore(d.id)}>Restore</button>
                  <button className="btn btn-ghost" onClick={() => setDeleteTarget(d)}>Delete</button>
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="token-panel">
          <h2>Connect orchestra</h2>
          <p>Mint a long-lived access token and save it to your creds file so the agent can beam to your displays.</p>
          <button className="btn btn-primary" onClick={mint}>Mint a token</button>

          {credsSnippet && (
            <div className="token-reveal">
              <p>Save to <code>~/.config/orchestra/botbeam.json</code> — shown once:</p>
              <pre className="setup-codeblock"><code>{credsSnippet}</code></pre>
              <button className="btn btn-primary btn-copy" onClick={() => copy(credsSnippet)}>
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Permanent delete confirmation */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setDeleteTarget(null); }}>
          <div className="modal">
            <h2>Delete "{deleteTarget.name}" permanently?</h2>
            <p style={{ color: 'var(--text-muted)', margin: '0 0 20px' }}>
              This removes the archived tab and its content for good. This can't be undone.
            </p>
            <div className="actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={() => destroy(deleteTarget.id)}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
