/**
 * Layout: MobileNav — Bottom tab navigation for mobile/PWA.
 * Shows all key sections. Sessions tab opens a bottom drawer.
 */

import { useState } from 'react';
import { NavLink, useLocation } from 'react-router';
import { Home, Users, Store, Clock, Monitor, Image as ImageIcon, Settings, Menu, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import MobileSessionDrawer from '@/components/layout/MobileSessionDrawer';

const PRIMARY_TABS = [
  { to: '/dashboard', icon: Home, label: 'Home' },
  { to: '/personas', icon: Users, label: 'Personas' },
  { to: '/mcp-store', icon: Store, label: 'MCP' },
  { id: 'sessions-drawer', icon: Clock, label: 'Sessions' },
  { id: 'more', icon: Menu, label: 'More' },
];

const MORE_ITEMS = [
  { to: '/clients', icon: Monitor, label: 'Clients' },
  { to: '/gallery', icon: ImageIcon, label: 'Gallery' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function MobileNav() {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <>
      {/* More menu overlay */}
      {moreOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setMoreOpen(false)}>
          <div className="absolute bottom-16 right-2 rounded-xl border border-border bg-card p-1 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            {MORE_ITEMS.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setMoreOpen(false)}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-4 py-2.5 text-sm transition-colors',
                  location.pathname.startsWith(to)
                    ? 'bg-white/8 text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon size={16} />
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      )}

      <nav className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-around border-t border-border/40 bg-[var(--background)]/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)] md:hidden">
        {PRIMARY_TABS.map(({ to, id, icon: Icon, label }) => {
          if (id === 'sessions-drawer') {
            return (
              <button
                key={id}
                onClick={() => setDrawerOpen(true)}
                className={cn(
                  'flex flex-col items-center gap-0.5 px-3 py-2 text-[10px] transition-colors',
                  drawerOpen || location.pathname.startsWith('/sessions') || location.pathname.startsWith('/session/')
                    ? 'text-foreground'
                    : 'text-muted-foreground',
                )}
              >
                <Icon size={18} />
                <span>{label}</span>
              </button>
            );
          }

          if (id === 'more') {
            const isMoreActive = MORE_ITEMS.some((i) => location.pathname.startsWith(i.to));
            return (
              <button
                key={id}
                onClick={() => setMoreOpen(!moreOpen)}
                className={cn(
                  'flex flex-col items-center gap-0.5 px-3 py-2 text-[10px] transition-colors',
                  moreOpen || isMoreActive ? 'text-foreground' : 'text-muted-foreground',
                )}
              >
                {moreOpen ? <X size={18} /> : <Icon size={18} />}
                <span>{label}</span>
              </button>
            );
          }

          const isActive = to === '/dashboard'
            ? location.pathname === '/dashboard' || location.pathname.startsWith('/session/')
            : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                'flex flex-col items-center gap-0.5 px-3 py-2 text-[10px] transition-colors',
                isActive ? 'text-foreground' : 'text-muted-foreground',
              )}
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          );
        })}
      </nav>

      <MobileSessionDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </>
  );
}
