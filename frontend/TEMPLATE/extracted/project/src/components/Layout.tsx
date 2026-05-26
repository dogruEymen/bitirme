import { NavLink, Outlet } from 'react-router-dom';
import { MessageSquare, BarChart3, Newspaper } from 'lucide-react';

const navItems = [
  { to: '/', icon: MessageSquare, label: 'Chat' },
  { to: '/dashboard', icon: BarChart3, label: 'Analytics' },
  { to: '/bulletin', icon: Newspaper, label: 'Bulletin' },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Sidebar */}
      <aside className="w-16 lg:w-56 bg-slate-900 flex flex-col shrink-0">
        <div className="h-16 flex items-center px-4 border-b border-slate-800">
          <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center">
            <span className="text-white font-bold text-sm">AC</span>
          </div>
          <span className="hidden lg:block ml-3 text-white font-semibold text-sm tracking-wide">
            AcademicAI
          </span>
        </div>

        <nav className="flex-1 py-4 space-y-1 px-2">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                }`
              }
            >
              <Icon size={18} />
              <span className="hidden lg:block">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-800">
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
              <span className="text-slate-300 text-xs font-medium">U</span>
            </div>
            <div className="hidden lg:block">
              <p className="text-slate-300 text-sm font-medium">Researcher</p>
              <p className="text-slate-500 text-xs">Academic Plan</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  );
}
