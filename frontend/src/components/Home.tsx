import { useCallback, useEffect, useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import { settings } from '../config/settings';
import { TYPE_META } from '../lib/contentMeta';
import type { Device } from '../types';
import DeviceCard from './DeviceCard';

export default function Home() {
  const { devices, displays, switchTab, user, logout, unarchiveDevice } = useBotBeam();
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [archived, setArchived] = useState<Device[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Device | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);

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

  function copy(text: string, key: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  const credsSnippet = newToken
    ? JSON.stringify({ base_url: settings.publicUrl, token: newToken }, null, 2)
    : null;

  const skillInstall =
    'git clone https://github.com/orchestrator-studios/botbeam\n' +
    'cp -r botbeam/skill/botbeam ~/.claude/skills/botbeam';
  const skillVerify = 'python ~/.claude/skills/botbeam/scripts/botbeam.py list';

  return (
    <div className="main home-view">
      <div className="home-content">
        <div className="home-account">
          <span>Signed in as <strong>{user}</strong></span>
          <button className="btn btn-ghost" onClick={logout}>Sign out</button>
        </div>

        {displays.length > 0 && (
          <div className="device-grid">
            {displays.map((d) => (
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
          <button
            className="token-panel-toggle"
            onClick={() => setConnectOpen((o) => !o)}
            aria-expanded={connectOpen}
          >
            <span className={`token-panel-caret ${connectOpen ? 'open' : ''}`}>▸</span>
            <span className="token-panel-heading">
              <strong>Connect an agent</strong>
              <span className="token-panel-sub">Mint a token and wire up orchestra or Claude Code</span>
            </span>
          </button>

          {connectOpen && (
          <div className="token-panel-body">
          <p>Mint a long-lived access token, then drop it in your creds file so orchestra or Claude Code can beam to your displays.</p>
          <button className="btn btn-primary" onClick={mint}>Mint a token</button>

          {credsSnippet && (
            <div className="token-reveal">
              <p>Save to <code>~/.config/orchestra/botbeam.json</code> — shown once:</p>
              <pre className="setup-codeblock"><code>{credsSnippet}</code></pre>
              <button className="btn btn-primary btn-copy" onClick={() => copy(credsSnippet, 'creds')}>
                {copied === 'creds' ? 'Copied!' : 'Copy'}
              </button>
            </div>
          )}

          <div className="setup-clients">
            <div className="setup-client">
              <h3>orchestra</h3>
              <p>
                Enable the bundled <code>botbeam</code> skill. It reads the creds file above automatically —
                nothing else to install.
              </p>
            </div>

            <div className="setup-client">
              <h3>Claude Code</h3>
              <ol className="setup-steps">
                <li>
                  Install the skill into your skills directory (Python 3 only, no third-party deps):
                  <pre className="setup-codeblock"><code>{skillInstall}</code></pre>
                  <button className="btn btn-ghost btn-copy" onClick={() => copy(skillInstall, 'install')}>
                    {copied === 'install' ? 'Copied!' : 'Copy'}
                  </button>
                </li>
                <li>Mint a token above and save it to <code>~/.config/orchestra/botbeam.json</code>.</li>
                <li>
                  Verify the connection:
                  <pre className="setup-codeblock"><code>{skillVerify}</code></pre>
                  <button className="btn btn-ghost btn-copy" onClick={() => copy(skillVerify, 'verify')}>
                    {copied === 'verify' ? 'Copied!' : 'Copy'}
                  </button>
                </li>
                <li>
                  That's it. For ways to use BotBeam and answers to common questions, see the{' '}
                  <button className="link-inline" onClick={() => switchTab('help')}>Help</button> section.
                </li>
              </ol>
            </div>
          </div>

          <p className="setup-more">
            New here? The <button className="link-inline" onClick={() => switchTab('help')}>Help</button> tab
            explains what BotBeam is for, with examples and an FAQ.
          </p>
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
