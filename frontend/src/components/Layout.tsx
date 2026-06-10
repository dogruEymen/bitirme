import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useCallback, useEffect, useState } from 'react';
import { BarChart3, LogOut, Menu, MessageSquare, Moon, Newspaper, Plus, Sun, Trash2, X } from 'lucide-react';
import { getBackendBaseUrl } from '../api/client';
import { clearStoredUser, getAuthHeaders, getStoredUser } from '../lib/auth';
import { ConfirmDialog } from './ui';

interface ChatSession {
  id: string;
  title: string;
}

const navItems = [
  { to: '/bulletin', icon: Newspaper, label: 'Bulletin' },
  { to: '/dashboard', icon: BarChart3, label: 'Analytics' },
];

export default function Layout() {
  const [user, setUser] = useState(getStoredUser());
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingDeleteSession, setPendingDeleteSession] = useState<ChatSession | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const stored = window.localStorage.getItem('academic_ai_theme');
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const navigate = useNavigate();
  const location = useLocation();
  const backendBaseUrl = getBackendBaseUrl();

  const applyTheme = (nextTheme: 'dark' | 'light') => {
    if (nextTheme === 'dark') {
      document.documentElement.classList.add('dark');
      document.body.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.body.classList.remove('dark');
    }
    document.documentElement.style.colorScheme = nextTheme;
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem('academic_ai_theme', nextTheme);
    setTheme(nextTheme);
  };

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    setUser(getStoredUser());
    setSidebarOpen(false);
  }, [location.pathname]);

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data: ChatSession[] = await response.json();
        setSessions(data);
      } else if (response.status === 401) {
        clearStoredUser();
        setUser(null);
        setSessions([]);
        navigate('/auth');
      }
    } catch (error) {
      console.error('Unable to fetch chat sessions', error);
    } finally {
      setLoadingSessions(false);
    }
  }, [backendBaseUrl, navigate]);

  useEffect(() => {
    if (!user) {
      setSessions([]);
      setLoadingSessions(false);
      return;
    }
    fetchSessions();
    const listener = () => fetchSessions();
    window.addEventListener('sessions-updated', listener);
    return () => window.removeEventListener('sessions-updated', listener);
  }, [fetchSessions, user]);

  const handleLogout = () => {
    clearStoredUser();
    setUser(null);
    navigate('/auth');
  };

  const handleCreateSession = () => {
    if (!user) {
      navigate('/auth');
      return;
    }
    navigate('/session/new');
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        setSessions((prev) => prev.filter((session) => session.id !== sessionId));
        window.dispatchEvent(new Event('sessions-updated'));
        if (location.pathname === `/session/${sessionId}`) {
          navigate('/session/new');
        }
      } else if (response.status === 401) {
        clearStoredUser();
        setUser(null);
        navigate('/auth');
      }
    } catch (error) {
      console.error('Failed to delete session', error);
    }
  };

  const sidebar = (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] text-[var(--text-primary)]">
      <div className="h-16 px-4 flex items-center justify-between border-b border-[var(--border)]">
        <button
          type="button"
          onClick={handleCreateSession}
          className="flex min-w-0 items-center gap-3 text-left"
        >
          <div className="h-9 w-9 rounded-full border border-[var(--border)] bg-[var(--surface-elevated)] flex items-center justify-center">
            <span className="text-sm font-semibold">A</span>
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-none">AcademicAI</p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">Research workspace</p>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-secondary)] md:hidden"
          aria-label="Close sidebar"
        >
          <X size={16} />
        </button>
      </div>

      <div className="px-3 py-4 space-y-1">
        <div className="px-3 pb-2">
          <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">Navigation</span>
        </div>

        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? 'border border-[var(--border)] bg-[var(--surface-elevated)] text-[var(--text-primary)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]'
              }`
            }
          >
            <Icon size={17} />
            <span>{label}</span>
          </NavLink>
        ))}

        <div className="pt-4">
          <button
            type="button"
            onClick={handleCreateSession}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--text-primary)] px-4 py-2.5 text-sm font-semibold text-[var(--canvas)] transition hover:opacity-90"
          >
            <Plus size={16} />
            New Chat
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 border-t border-[var(--border)] px-3 py-4">
        <div className="mb-3 flex items-center justify-between px-3">
          <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">Chat sessions</span>
          <span className="text-xs text-[var(--text-muted)]">{sessions.length}</span>
        </div>

        <div className="h-full space-y-1 overflow-y-auto pr-1">
          {loadingSessions ? (
            <div className="flex items-center justify-center py-6">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--text-muted)] border-t-[var(--text-primary)]" />
            </div>
          ) : sessions.length === 0 ? (
            <p className="px-3 text-xs leading-5 text-[var(--text-muted)]">No sessions yet.</p>
          ) : (
            sessions.map((session) => {
              const isActive = location.pathname === `/session/${session.id}`;
              return (
                <div
                  key={session.id}
                  className={`group relative rounded-lg ${
                    isActive ? 'border border-[var(--border)] bg-[var(--surface-elevated)]' : 'hover:bg-[var(--surface-elevated)]'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => navigate(`/session/${session.id}`)}
                    className="flex w-full items-center gap-3 rounded-lg py-2.5 pl-3 pr-10 text-left text-sm font-medium text-[var(--text-secondary)] transition hover:text-[var(--text-primary)]"
                  >
                    <MessageSquare size={16} className={isActive ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'} />
                    <span className="truncate">{session.title}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingDeleteSession(session)}
                    title="Delete"
                    aria-label="Delete session"
                    className="absolute right-1.5 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-[var(--text-muted)] opacity-0 transition hover:bg-[var(--surface-high)] hover:text-[var(--text-primary)] group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div className="border-t border-[var(--border)] p-3">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-3">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-muted)]">Account</p>
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface)] text-sm font-semibold text-[var(--text-primary)]">
              {user ? user.username[0]?.toUpperCase() : 'G'}
            </div>
            <div className="min-w-0 flex-1 text-sm">
              <p className="truncate font-semibold text-[var(--text-primary)]">{user ? user.username : 'Guest user'}</p>
              <p className="truncate text-xs text-[var(--text-muted)]">{user ? user.email : 'Sign in to save chats'}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => applyTheme(theme === 'dark' ? 'light' : 'dark')}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)] transition hover:bg-[var(--surface-high)] hover:text-[var(--text-primary)]"
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
          </button>
          {user && (
            <button
              type="button"
              onClick={handleLogout}
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-xs font-semibold uppercase tracking-[0.05em] text-[var(--text-secondary)] transition hover:bg-[var(--surface-high)] hover:text-[var(--text-primary)]"
            >
              <LogOut size={14} />
              Logout
            </button>
          )}
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex min-h-screen bg-[var(--canvas)] text-[var(--text-primary)]">
      <div className="hidden md:block">{sidebar}</div>

      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close sidebar overlay"
            className="absolute inset-0 bg-black/70"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="relative h-full">{sidebar}</div>
        </div>
      )}

      <main className="min-w-0 flex-1 overflow-hidden bg-[var(--canvas)]">
        <div className="flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-4 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-secondary)]"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
          <span className="text-sm font-semibold">AcademicAI</span>
          <button
            type="button"
            onClick={handleCreateSession}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-secondary)]"
            aria-label="New chat"
          >
            <Plus size={18} />
          </button>
        </div>
        <div className="h-[calc(100vh-3.5rem)] overflow-hidden md:h-screen">
          <Outlet />
        </div>
      </main>

      <ConfirmDialog
        open={Boolean(pendingDeleteSession)}
        title="Delete chat session?"
        body={`This will permanently remove "${pendingDeleteSession?.title || 'this session'}" from your workspace.`}
        confirmLabel="Delete"
        destructive
        onCancel={() => setPendingDeleteSession(null)}
        onConfirm={() => {
          if (pendingDeleteSession) {
            handleDeleteSession(pendingDeleteSession.id);
            setPendingDeleteSession(null);
          }
        }}
      />
    </div>
  );
}
