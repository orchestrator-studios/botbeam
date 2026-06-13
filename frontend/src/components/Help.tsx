import { useBotBeam } from '../context/BotBeamContext';

// In-app Help / docs section. The user-facing companion to the skill's SKILL.md:
// what BotBeam is for (presentation mode), how to get going, and an FAQ.
const CONTENT_TYPES: { label: string; desc: string }[] = [
  { label: 'Markdown', desc: 'Formatted notes, briefs, write-ups.' },
  { label: 'Dashboard', desc: 'KPI cards — headline numbers at a glance.' },
  { label: 'Table', desc: 'Rows and records.' },
  { label: 'List', desc: 'Bullets or a checklist (with checkboxes).' },
  { label: 'URL', desc: 'A live web page, embedded.' },
  { label: 'Image', desc: 'An image by URL.' },
  { label: 'HTML', desc: 'Custom rendered markup.' },
  { label: 'JSON', desc: 'Raw data, pretty-printed.' },
  { label: 'Text', desc: 'Plain, unformatted text.' },
];

export default function Help() {
  const { switchTab } = useBotBeam();

  return (
    <div className="main home-view">
      <div className="home-content help-doc">
        <h1>Using BotBeam</h1>
        <p className="help-lede">
          BotBeam is a <strong>second channel</strong> running alongside your conversation with an agent.
          The chat scrolls past; a beamed view <strong>stays put</strong> — a fixed place to set the thing
          you're discussing, like a handout, a slide, or something written on the whiteboard while you keep
          talking. The dialogue is the talking; the display is what's on the wall.
        </p>

        <section className="help-section">
          <h2>When to use it</h2>
          <p>Reach for it whenever a result is better <em>shown</em> than read past in a terminal or buried in chat:</p>
          <ul>
            <li><strong>Ask for an artifact, not a wall of text.</strong> "Summarize these five reports" → your agent beams a clean brief or a dashboard of the key numbers and walks you through it.</li>
            <li><strong>Keep something in view.</strong> A figure you'll point back to ("as you can see on your screen…") while the conversation moves on around it.</li>
            <li><strong>Watch work happen.</strong> A dashboard or checklist the agent updates in place as a task runs.</li>
            <li><strong>Stash for later.</strong> "Keep this handy for the call" → it goes to a lockbox, off-screen, without cluttering your display now.</li>
          </ul>
        </section>

        <section className="help-section">
          <h2>Get started</h2>
          <ol className="help-steps">
            <li>
              Connect an agent from the{' '}
              <button className="link-inline" onClick={() => switchTab('home')}>Home</button>{' '}
              tab — mint a token and wire up orchestra or Claude Code.
            </li>
            <li>Try it: ask your agent to <em>"beam a hello-world to my main display."</em> It should appear here live, no refresh.</li>
            <li>
              <strong>Ask your agent to explain the skill</strong> — e.g. <em>"what can you do with botbeam?"</em>{' '}
              This confirms the agent can actually see it, and the answer is a quick, tailored tour of what's possible.
            </li>
          </ol>
        </section>

        <section className="help-section">
          <h2>What you can show</h2>
          <dl className="help-types">
            {CONTENT_TYPES.map((t) => (
              <div className="help-type" key={t.label}>
                <dt>{t.label}</dt>
                <dd>{t.desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="help-section">
          <h2>Displays, lockboxes, sharing &amp; pinning</h2>
          <ul>
            <li><strong>Displays</strong> are tabs you watch live. Everyone has a <strong>Main</strong> display; your agent can also create named tabs like "Pipeline" or "OKRs."</li>
            <li><strong>Lockboxes</strong> are stashed off-screen in the side panel — saved for later or handed between sessions, without disturbing what's on screen.</li>
            <li><strong>Sharing:</strong> give another BotBeam user <em>view-only</em> access to a display with the <strong>Share</strong> button. You point to them by the email address they registered with — that's just their account name, not a way of emailing anything. The display then appears under their "Shared with me" and tracks your beams live.</li>
            <li><strong>Pinning:</strong> pin a display (the 📌 on a tab, or open <code>?pin=&lt;name&gt;</code>) to lock a browser to just that display, kiosk-style — ideal for a wall screen, a meeting room, or a kitchen display.</li>
          </ul>
        </section>

        <section className="help-section">
          <h2>FAQ</h2>
          <dl className="help-faq">
            <dt>Where does what I beam show up?</dt>
            <dd>By default on your <strong>Main</strong> display, updated in place. Your agent can also put content on a new named tab, or stash it in a lockbox (the side panel) instead of on screen.</dd>

            <dt>What's the difference between beaming and stashing?</dt>
            <dd>Beaming puts something on screen now. Stashing saves it for later — in a lockbox — without touching what's currently displayed. Same store, just shown or set aside.</dd>

            <dt>Will a new beam wipe what's already up?</dt>
            <dd>No — updating one display only replaces that display's content. <em>Reset</em> is the only action that clears everything (your Main display survives, blanked), so agents confirm before doing it.</dd>

            <dt>Can someone else see my display?</dt>
            <dd>Only if you share it. Use the <strong>Share</strong> button on a display and enter the email the other person signed up to BotBeam with — that's how their account is identified, not a way of emailing them anything. They get view-only access under their "Shared with me," updating live as you beam.</dd>

            <dt>Can I dedicate a screen to one display?</dt>
            <dd>Yes — pin it. A pinned browser shows only that display and won't follow beams to other tabs. Great for a screen on the wall. Unpin from the bar at the top.</dd>

            <dt>It's not updating live — what's wrong?</dt>
            <dd>Most often the browser and the agent are pointed at different BotBeam hosts (they can share data but not live updates). Make sure both use the same base URL. A sign-in error means the agent's token expired — re-mint it from Home.</dd>
          </dl>
        </section>
      </div>
    </div>
  );
}
