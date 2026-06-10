import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ensureOk, getBackendBaseUrl, normalizeUnknownError } from '../api/client';
import { getAuthHeaders, getStoredUser, setStoredUser } from '../lib/auth';

const backendBaseUrl = getBackendBaseUrl();

export default function AuthPage() {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const user = getStoredUser();
    if (user) {
      navigate('/session/new');
    }
  }, [navigate]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    const endpoint = mode === 'signup' ? '/auth/signup' : '/auth/login';
    const payload: Record<string, string> = { email, password };
    if (mode === 'signup') payload.username = username;

    setIsSubmitting(true);
    try {
      const response = await fetch(`${backendBaseUrl}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(payload),
      });

      await ensureOk(response);
      const user = await response.json();
      setStoredUser(user);
      navigate('/');
    } catch (error) {
      setError(normalizeUnknownError(error, 'Network error. Please try again.').message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-[var(--canvas)] px-4 py-8">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">AcademicAI Account</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            {mode === 'signup' ? 'Create a new account to save your chats.' : 'Sign in to continue and access your sessions.'}
          </p>
        </div>

        <div className="mb-6 flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => setMode('login')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'login'
                ? 'bg-[var(--text-primary)] text-[var(--canvas)]'
                : 'border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            Login
          </button>
          <button
            type="button"
            onClick={() => setMode('signup')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'signup'
                ? 'bg-[var(--text-primary)] text-[var(--canvas)]'
                : 'border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'signup' && (
            <label className="block text-sm font-medium text-[var(--text-secondary)]">
              Username
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--text-primary)]"
              />
            </label>
          )}

          <label className="block text-sm font-medium text-[var(--text-secondary)]">
            Email address
            <input
              value={email}
              type="email"
              onChange={e => setEmail(e.target.value)}
              required
              className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--text-primary)]"
            />
          </label>

          <label className="block text-sm font-medium text-[var(--text-secondary)]">
            Password
            <input
              value={password}
              type="password"
              onChange={e => setPassword(e.target.value)}
              required
              className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--text-primary)]"
            />
          </label>

          {mode === 'signup' && (
            <label className="block text-sm font-medium text-[var(--text-secondary)]">
              Confirm Password
              <input
                value={confirmPassword}
                type="password"
                onChange={e => setConfirmPassword(e.target.value)}
                required
                className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--text-primary)]"
              />
            </label>
          )}

          {error && <p className="text-sm text-[var(--danger)]">{error}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-[var(--text-primary)] px-4 py-3 text-sm font-semibold text-[var(--canvas)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Please wait...' : mode === 'signup' ? 'Create account' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
