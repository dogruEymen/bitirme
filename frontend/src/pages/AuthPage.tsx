import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { getBackendBaseUrl } from '../api/client';
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

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setError(body?.detail || 'Unable to authenticate.');
      } else {
        const user = await response.json();
        setStoredUser(user);
        navigate('/');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-black px-4 py-8">
      <div className="w-full max-w-md rounded-2xl border border-[#2f2f2f] bg-[#0d0d0d] p-8">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-white">AcademicAI Account</h1>
          <p className="mt-2 text-sm text-[#b4b4b4]">
            {mode === 'signup' ? 'Create a new account to save your chats.' : 'Sign in to continue and access your sessions.'}
          </p>
        </div>

        <div className="mb-6 flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => setMode('login')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'login'
                ? 'bg-white text-black'
                : 'border border-[#2f2f2f] bg-[#171717] text-[#b4b4b4] hover:text-white'
            }`}
          >
            Login
          </button>
          <button
            type="button"
            onClick={() => setMode('signup')}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              mode === 'signup'
                ? 'bg-white text-black'
                : 'border border-[#2f2f2f] bg-[#171717] text-[#b4b4b4] hover:text-white'
            }`}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'signup' && (
            <label className="block text-sm font-medium text-[#b4b4b4]">
              Username
              <input
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                className="mt-2 w-full rounded-lg border border-[#2f2f2f] bg-[#171717] px-4 py-3 text-sm text-white outline-none transition focus:border-white"
              />
            </label>
          )}

          <label className="block text-sm font-medium text-[#b4b4b4]">
            Email address
            <input
              value={email}
              type="email"
              onChange={e => setEmail(e.target.value)}
              required
              className="mt-2 w-full rounded-lg border border-[#2f2f2f] bg-[#171717] px-4 py-3 text-sm text-white outline-none transition focus:border-white"
            />
          </label>

          <label className="block text-sm font-medium text-[#b4b4b4]">
            Password
            <input
              value={password}
              type="password"
              onChange={e => setPassword(e.target.value)}
              required
              className="mt-2 w-full rounded-lg border border-[#2f2f2f] bg-[#171717] px-4 py-3 text-sm text-white outline-none transition focus:border-white"
            />
          </label>

          {mode === 'signup' && (
            <label className="block text-sm font-medium text-[#b4b4b4]">
              Confirm Password
              <input
                value={confirmPassword}
                type="password"
                onChange={e => setConfirmPassword(e.target.value)}
                required
                className="mt-2 w-full rounded-lg border border-[#2f2f2f] bg-[#171717] px-4 py-3 text-sm text-white outline-none transition focus:border-white"
              />
            </label>
          )}

          {error && <p className="text-sm text-[#ffb4ab]">{error}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-white px-4 py-3 text-sm font-semibold text-black transition hover:bg-[#e2e2e2] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Please wait...' : mode === 'signup' ? 'Create account' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
