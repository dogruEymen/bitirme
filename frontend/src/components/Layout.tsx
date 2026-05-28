import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { BarChart3, LogOut, Menu, MessageSquare, Newspaper, Plus, Trash2, X } from 'lucide-react';
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    setSidebarOpen(false);
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

  const sidebar = (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-r border-[#2f2f2f] bg-[#0d0d0d] text-white">
      <div className="h-16 px-4 flex items-center justify-between border-b border-[#2f2f2f]">
        <button
          type="button"
          onClick={handleCreateSession}
          className="flex min-w-0 items-center gap-3 text-left"
        >
          <div className="h-9 w-9 rounded-full border border-[#2f2f2f] bg-[#171717] flex items-center justify-center">
            <span className="text-sm font-semibold">A</span>
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold leading-none">AcademicAI</p>
            <p className="mt-1 text-xs text-[#767676]">Research workspace</p>
          </div>
        </button>
        <button
          type="button"
          onClick={() => setSidebarOpen(false)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#2f2f2f] text-[#b4b4b4] md:hidden"
          aria-label="Close sidebar"
        >
          <X size={16} />
        </button>
      </div>

      <div className="px-3 py-4 space-y-1">
        <div className="px-3 pb-2">
          <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[#767676]">Navigation</span>
        </div>

        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? 'border border-[#2f2f2f] bg-[#171717] text-white'
                  : 'text-[#b4b4b4] hover:bg-[#171717] hover:text-white'
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
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-black transition hover:bg-[#e2e2e2]"
          >
            <Plus size={16} />
            New Chat
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 border-t border-[#2f2f2f] px-3 py-4">
        <div className="mb-3 flex items-center justify-between px-3">
          <span className="text-xs font-semibold uppercase tracking-[0.05em] text-[#767676]">Chat sessions</span>
          <span className="text-xs text-[#767676]">{sessions.length}</span>
        </div>

        <div className="h-full space-y-1 overflow-y-auto pr-1">
          {loadingSessions ? (
            <div className="flex items-center justify-center py-6">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#767676] border-t-white" />
            </div>
          ) : sessions.length === 0 ? (
            <p className="px-3 text-xs leading-5 text-[#767676]">No sessions yet.</p>
          ) : (
            sessions.map((session) => {
              const isActive = location.pathname === `/session/${session.id}`;
              return (
                <div
                  key={session.id}
                  className={`group relative rounded-lg ${
                    isActive ? 'border border-[#2f2f2f] bg-[#171717]' : 'hover:bg-[#171717]'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => navigate(`/session/${session.id}`)}
                    className="flex w-full items-center gap-3 rounded-lg py-2.5 pl-3 pr-10 text-left text-sm font-medium text-[#b4b4b4] transition hover:text-white"
                  >
                    <MessageSquare size={16} className={isActive ? 'text-white' : 'text-[#767676]'} />
                    <span className="truncate">{session.title}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteSession(session.id)}
                    title="Delete"
                    aria-label="Delete session"
                    className="absolute right-1.5 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-[#767676] opacity-0 transition hover:bg-[#1f1f1f] hover:text-white group-hover:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      <div className="border-t border-[#2f2f2f] p-3">
        <div className="rounded-lg border border-[#2f2f2f] bg-[#171717] p-3">
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.05em] text-[#767676]">Account</p>
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#2f2f2f] bg-[#0d0d0d] text-sm font-semibold text-white">
              {user ? user.username[0]?.toUpperCase() : 'G'}
            </div>
            <div className="min-w-0 flex-1 text-sm">
              <p className="truncate font-semibold text-white">{user ? user.username : 'Guest user'}</p>
              <p className="truncate text-xs text-[#767676]">{user ? user.email : 'Sign in to save chats'}</p>
            </div>
          </div>
          {user && (
            <button
              type="button"
              onClick={handleLogout}
              className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[#2f2f2f] px-3 py-2 text-xs font-semibold uppercase tracking-[0.05em] text-[#b4b4b4] transition hover:bg-[#1f1f1f] hover:text-white"
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
    <div className="flex min-h-screen bg-black text-white">
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

      <main className="min-w-0 flex-1 overflow-hidden bg-black">
        <div className="flex h-14 items-center justify-between border-b border-[#2f2f2f] bg-[#0d0d0d] px-4 md:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#2f2f2f] text-[#b4b4b4]"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
          <span className="text-sm font-semibold">AcademicAI</span>
          <button
            type="button"
            onClick={handleCreateSession}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#2f2f2f] text-[#b4b4b4]"
            aria-label="New chat"
          >
            <Plus size={18} />
          </button>
        </div>
        <div className="h-[calc(100vh-3.5rem)] overflow-hidden md:h-screen">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
