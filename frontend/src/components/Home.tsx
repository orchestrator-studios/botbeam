import { useState } from 'react';
import { useBotBeam } from '../context/BotBeamContext';
import { botbeamApi } from '../lib/api/botbeamApi';
import { settings } from '../config/settings';
import DeviceCard from './DeviceCard';

export default function Home() {
  const { devices, switchTab, user, logout } = useBotBeam();
  const [newToken, setNewToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const displayDevices = devices.filter((d) => !d.pickupMode);

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

        {displayDevices.length > 0 && (
          <div className="device-grid">
            {displayDevices.map((d) => (
              <DeviceCard key={d.id} device={d} onClick={() => switchTab(d.id)} />
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
    </div>
  );
}
