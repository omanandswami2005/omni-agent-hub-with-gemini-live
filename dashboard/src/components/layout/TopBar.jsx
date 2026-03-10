/**
 * Layout: TopBar — Top navigation bar with search, user menu, theme toggle.
 */

import { Search, Menu } from 'lucide-react';
import ThemeToggle from '@/components/layout/ThemeToggle';
import UserMenu from '@/components/auth/UserMenu';
import ClientStatusBar from '@/components/clients/ClientStatusBar';
import { useUiStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { useClientStore } from '@/stores/clientStore';

export default function TopBar() {
  const { toggleSidebar, setCommandPalette } = useUiStore();
  const { user } = useAuthStore();
  const { clients } = useClientStore();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border px-4">
      {/* Left: hamburger (mobile) + search */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="rounded-md p-1.5 hover:bg-accent md:hidden"
          aria-label="Toggle menu"
        >
          <Menu size={20} />
        </button>
        <button
          onClick={() => setCommandPalette(true)}
          className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
        >
          <Search size={14} />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="ml-2 hidden rounded border border-border px-1.5 py-0.5 text-[10px] font-mono sm:inline">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right: clients, theme, user */}
      <div className="flex items-center gap-3">
        <ClientStatusBar clients={clients} />
        <ThemeToggle />
        {user && <UserMenu user={user} onSignOut={() => useAuthStore.getState().logout()} />}
      </div>
    </header>
  );
}
