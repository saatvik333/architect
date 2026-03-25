import { NavLink, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

interface LayoutProps {
  children: ReactNode;
}

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const navSections: NavSection[] = [
  {
    title: 'Monitor',
    items: [
      { to: '/tasks',     label: 'Tasks',     icon: '\u25B6' },
      { to: '/health',    label: 'Health',    icon: '\u25C8' },
      { to: '/proposals', label: 'Proposals', icon: '\u25C6' },
    ],
  },
  {
    title: 'Human Interface',
    items: [
      { to: '/escalations', label: 'Escalations', icon: '\u26A0' },
      { to: '/progress',    label: 'Progress',    icon: '\u25CE' },
      { to: '/budget',      label: 'Budget',      icon: '\u25A3' },
      { to: '/activity',    label: 'Activity',    icon: '\u25CF' },
    ],
  },
];

const routeLabels: Record<string, string> = {
  '/tasks':       'Tasks',
  '/health':      'Health',
  '/proposals':   'Proposals',
  '/escalations': 'Escalations',
  '/progress':    'Progress',
  '/budget':      'Budget',
  '/activity':    'Activity',
};

function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  const section = routeLabels[pathname] ?? routeLabels[Object.keys(routeLabels).find(k => pathname.startsWith(k)) ?? ''] ?? 'Monitor';

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* ── Sidebar ─────────────────────────────────────────── */}
      <aside className="w-52 flex-shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-gray-700">
          <h1 className="architect-wordmark">ARCHITECT</h1>
          <p className="text-gray-500 mt-1" style={{ fontSize: '10px', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Autonomous Coding System
          </p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 overflow-y-auto">
          {navSections.map((section) => (
            <div key={section.title}>
              <div className="px-2 pt-4 pb-2">
                <span className="text-gray-500" style={{ fontSize: '9px', letterSpacing: '0.14em', textTransform: 'uppercase', fontWeight: 600 }}>
                  {section.title}
                </span>
              </div>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                  >
                    <span style={{ fontSize: '10px', opacity: 0.75 }}>{item.icon}</span>
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-700 flex items-center gap-2">
          <span
            className="rounded-full bg-green-400 inline-block"
            style={{ width: 6, height: 6, boxShadow: '0 0 6px #3fb950' }}
          />
          <span className="font-mono text-gray-500" style={{ fontSize: '10px' }}>v0.1.0</span>
        </div>
      </aside>

      {/* ── Main ────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <div className="h-11 flex-shrink-0 bg-gray-900 border-b border-gray-700 flex items-center px-6 gap-3">
          <span className="rounded-full bg-indigo-400 inline-block" style={{ width: 5, height: 5, boxShadow: '0 0 8px rgba(0,217,255,0.5)' }} />
          <span className="topbar-path">ARCHITECT / {section.toUpperCase()}</span>
        </div>

        {/* Content */}
        <main className="flex-1 overflow-auto">
          <div className="p-6">{children}</div>
        </main>
      </div>
    </div>
  );
}

export default Layout;
