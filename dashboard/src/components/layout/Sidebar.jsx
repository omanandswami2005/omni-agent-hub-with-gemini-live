/**
 * Layout: Sidebar — Navigation sidebar with route links and persona quick-switch.
 */

import { NavLink, useLocation } from 'react-router';
import {
  Home,
  Users,
  Store,
  Clock,
  Monitor,
  Settings,
  PanelLeftClose,
  PanelLeft,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useUiStore } from '@/stores/uiStore';
import { usePersonaStore } from '@/stores/personaStore';
import KeyboardShortcut from '@/components/shared/KeyboardShortcut';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: Home, shortcut: ['1'] },
  { to: '/personas', label: 'Personas', icon: Users, shortcut: ['2'] },
  { to: '/mcp-store', label: 'MCP Store', icon: Store, shortcut: ['3'] },
  { to: '/sessions', label: 'Sessions', icon: Clock, shortcut: ['4'] },
  { to: '/clients', label: 'Clients', icon: Monitor, shortcut: ['5'] },
  { to: '/settings', label: 'Settings', icon: Settings, shortcut: ['6'] },
];

export default function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUiStore();
  const { activePersona } = usePersonaStore();
  const location = useLocation();

  return (
    <aside
      className={cn(
        'hidden flex-col border-r border-border bg-[var(--sidebar)] text-[var(--sidebar-foreground)] transition-all duration-200 md:flex',
        sidebarOpen ? 'w-64' : 'w-16',
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        {sidebarOpen && <span className="text-lg font-bold">Omni</span>}
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 hover:bg-accent"
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, shortcut }) => {
          const isActive = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-accent text-accent-foreground font-medium'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
              )}
              title={label}
            >
              <Icon size={18} />
              {sidebarOpen && (
                <>
                  <span className="flex-1">{label}</span>
                  <KeyboardShortcut keys={shortcut} />
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Active persona indicator */}
      {sidebarOpen && activePersona && (
        <div className="border-t border-border p-3">
          <div className="flex items-center gap-2 rounded-lg bg-accent/50 px-3 py-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
              {activePersona.name?.[0] || '?'}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium">{activePersona.name}</p>
              <p className="truncate text-[10px] text-muted-foreground">{activePersona.tagline}</p>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
