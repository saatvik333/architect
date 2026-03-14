import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

const navItems = [
  { to: '/tasks', label: 'Tasks', icon: '▶' },
  { to: '/health', label: 'Health', icon: '♥' },
  { to: '/proposals', label: 'Proposals', icon: '◆' },
];

function Layout({ children }: LayoutProps) {
  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gray-950 border-r border-gray-800 flex flex-col">
        {/* Logo / Title */}
        <div className="px-6 py-5 border-b border-gray-800">
          <h1 className="text-xl font-bold tracking-wider text-indigo-400">
            ARCHITECT
          </h1>
          <p className="text-xs text-gray-500 mt-1">Autonomous Coding System</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-400'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-800 text-xs text-gray-600">
          v0.1.0
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}

export default Layout;
