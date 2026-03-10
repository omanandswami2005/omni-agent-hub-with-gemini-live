/**
 * Layout: MobileNav — Bottom tab navigation for mobile/PWA.
 */

import { NavLink, useLocation } from 'react-router';
import { Home, Users, Store, Clock, Settings } from 'lucide-react';
import { cn } from '@/lib/cn';

const TABS = [
  { to: '/', icon: Home, label: 'Home' },
  { to: '/personas', icon: Users, label: 'Personas' },
  { to: '/mcp-store', icon: Store, label: 'MCP' },
  { to: '/sessions', icon: Clock, label: 'Sessions' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function MobileNav() {
  const location = useLocation();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 flex items-center justify-around border-t border-border bg-[var(--background)] pb-[env(safe-area-inset-bottom)] md:hidden">
      {TABS.map(({ to, icon: Icon, label }) => {
        const isActive = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
        return (
          <NavLink
            key={to}
            to={to}
            className={cn(
              'flex flex-col items-center gap-0.5 px-3 py-2 text-[10px]',
              isActive ? 'text-primary' : 'text-muted-foreground',
            )}
          >
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
