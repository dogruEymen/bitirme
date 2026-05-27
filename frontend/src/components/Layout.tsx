import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { MessageSquare, BarChart3, Newspaper, Plus, Trash2 } from 'lucide-react';
import { clearStoredUser, getAuthHeaders, getStoredUser } from '../lib/auth';

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
  const navigate = useNavigate();
  const location = useLocation();
  const backendHost = window.location.hostname;

  const applyTheme = (isDark: boolean) => {
    const nextTheme = isDark ? 'dark' : 'light';
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.body.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.body.classList.remove('dark');
    }
    document.documentElement.style.colorScheme = nextTheme;
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem('academic_ai_theme', nextTheme);
  };
  const backendBaseUrl = `http://${backendHost}:8000`;

  useEffect(() => {
    const stored = window.localStorage.getItem('academic_ai_theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = stored ? stored === 'dark' : prefersDark;
    applyTheme(isDark);
  }, []);

  useEffect(() => {
    setUser(getStoredUser());
  }, [location.pathname]);

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
  }, [user]);

  const fetchSessions = async () => {
    setLoadingSessions(true);
    try {
      const response = await fetch(`${backendBaseUrl}/chat/sessions`, {
        headers: getAuthHeaders(),
      });
      if (response.ok) {
        const data: ChatSession[] = await response.json();
        setSessions(data);
      }
    } catch (error) {
      console.error('Unable to fetch chat sessions', error);
    } finally {
      setLoadingSessions(false);
    }
  };

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
      }
    } catch (error) {
      console.error('Failed to delete session', error);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex">
      <aside className="w-72 bg-white text-slate-900 flex flex-col shrink-0 border-r border-slate-200 dark:bg-slate-950 dark:text-slate-100 dark:border-slate-800">
        <div className="h-20 px-5 flex items-center border-b border-slate-200 dark:border-slate-800">
          <div className="w-10 h-10 rounded-2xl bg-emerald-500 flex items-center justify-center">
            <span className="text-white font-bold text-base">A</span>
          </div>
          <div className="ml-4">
            <p className="text-sm font-semibold">AcademicAI</p>
            <p className="text-xs text-slate-400">Research assistant</p>
          </div>
        </div>

        <div className="px-4 py-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Navigation</span>
          </div>

          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-2xl text-sm font-medium transition ${
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-white'
                }`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}

          <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={handleCreateSession}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-emerald-500 text-slate-950 font-semibold shadow-sm shadow-emerald-500/20 hover:bg-emerald-400 transition"
            >
              <Plus size={16} />
              New Chat
            </button>
          </div>
        </div>

        <div className="px-4 pt-4 pb-3 border-t border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase tracking-[0.18em] text-slate-500">Chat sessions</span>
            <span className="text-xs text-slate-500">{sessions.length}</span>
          </div>

          <div className="space-y-2 max-h-[calc(100vh-26rem)] overflow-y-auto pr-2">
            {loadingSessions ? (
              <div className="flex items-center justify-center py-6">
                <div className="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : sessions.length === 0 ? (
              <p className="text-xs text-slate-500 dark:text-slate-400">No sessions yet.</p>
            ) : (
              sessions.map((session) => {
                const isActive = location.pathname === `/session/${session.id}`;
                return (
                  <div
                    key={session.id}
                    className={`relative rounded-2xl overflow-hidden ${isActive ? 'bg-emerald-500/15' : 'bg-slate-100 dark:bg-slate-900/80'} group`}
                  >
                    <button
                      type="button"
                      onClick={() => handleDeleteSession(session.id)}
                      title="Delete"
                      aria-label="Delete session"
                      className="absolute top-2 right-2 z-10 rounded-full p-2 text-slate-400 transition hover:text-rose-400"
                    >
                      <Trash2 size={14} />
                      <span className="pointer-events-none absolute right-full top-1/2 hidden translate-x-2 -translate-y-1/2 whitespace-nowrap rounded-full bg-slate-950 px-2 py-1 text-[11px] text-slate-100 shadow-lg shadow-slate-950/50 group-hover:block">
                        Delete
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(`/session/${session.id}`)}
                      className="w-full text-left px-3 py-4 flex items-start gap-3 rounded-2xl text-sm font-medium text-slate-900 dark:text-slate-100"
                    >
                      <MessageSquare size={16} className={isActive ? 'text-emerald-400' : 'text-slate-400'} />
                      <span className="truncate">{session.title}</span>
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="mt-auto px-4 pb-5 pt-4 border-t border-slate-200 dark:border-slate-800">
          <div className="rounded-3xl bg-slate-100 px-4 py-4 border border-slate-200 dark:bg-slate-900 dark:border-slate-800">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500 mb-3">Account</p>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-900 font-semibold text-sm dark:bg-slate-800 dark:text-slate-300">
                {user ? user.username[0]?.toUpperCase() : 'G'}
              </div>
              <div className="flex-1 text-sm">
                <p className="text-slate-100 font-semibold">{user ? user.username : 'Guest user'}</p>
                <p className="text-slate-500 text-xs">{user ? user.email : 'Sign in to save chats'}</p>
              </div>
            </div>
            {user && (
              <button
                type="button"
                onClick={handleLogout}
                className="mt-4 w-full px-3 py-2 rounded-2xl bg-slate-100 text-slate-900 text-xs font-semibold uppercase tracking-[0.18em] hover:bg-slate-200 transition dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                Logout
              </button>
            )}
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden flex flex-col">
        <div className="flex-1 overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
