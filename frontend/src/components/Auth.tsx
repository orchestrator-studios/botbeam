import { useState, type FormEvent } from 'react';
import { useBotBeam } from '../context/BotBeamContext';

function humanize(err: unknown): string {
  const status = (err as { status?: number })?.status;
  if (status === 401) return 'Invalid email or password.';
  if (status === 409) return 'That email is already registered.';
  if (status === 400) return 'Check your email, and use a password of 8+ characters.';
  return 'Something went wrong. Try again.';
}

export default function Auth() {
  const { login, register } = useBotBeam();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      if (mode === 'login') await login(email, password);
      else await register(email, password);
    } catch (err) {
      setError(humanize(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>BotBeam</h1>
        <p className="auth-tagline">Sign in to your displays.</p>
        <form onSubmit={submit} className="auth-form">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
          />
          {error && <div className="auth-error">{error}</div>}
          <button className="btn btn-primary btn-large" disabled={busy} type="submit">
            {busy ? '…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <button
          className="auth-switch"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError('');
          }}
        >
          {mode === 'login' ? 'No account? Register' : 'Have an account? Sign in'}
        </button>
      </div>
    </div>
  );
}
