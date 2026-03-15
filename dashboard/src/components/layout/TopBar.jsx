/**
 * Layout: TopBar — Top navigation bar with search, center info, user menu.
 */

import { Search, Wifi, WifiOff, Zap } from 'lucide-react';
import ThemeToggle from '@/components/layout/ThemeToggle';
import UserMenu from '@/components/auth/UserMenu';
import ClientStatusBar from '@/components/clients/ClientStatusBar';
import { useAuth } from '@/hooks/useAuth';
import { useUiStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { useClientStore } from '@/stores/clientStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useChatStore } from '@/stores/chatStore';

export default function TopBar() {
  const { setCommandPalette } = useUiStore();
  const { signOut } = useAuth();
  const { user } = useAuthStore();
  const { clients } = useClientStore();
  const activePersona = usePersonaStore((s) => s.activePersona);
  const agentState = useChatStore((s) => s.agentState);
  const toolActivity = useChatStore((s) => s.toolActivity);
  const activeToolCount = Object.keys(toolActivity).length;

  return (
    <header className="flex h-14 items-center justify-between border-b border-white/[0.06] px-4">
      {/* Left: search */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setCommandPalette(true)}
          className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-white/[0.06]"
        >
          <Search size={14} />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="ml-2 hidden rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground/60 sm:inline">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Center: active persona + agent state + tool activity */}
      <div className="hidden items-center gap-3 sm:flex">
        {activePersona && (
          <div className="flex items-center gap-2 text-sm">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-foreground text-background text-[10px] font-bold">
              {activePersona.name?.charAt(0)?.toUpperCase() || 'A'}
            </div>
            <span className="text-foreground/80 font-medium text-xs">{activePersona.name}</span>
          </div>
        )}
        <div className="h-3 w-px bg-white/[0.08]" />
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          {agentState === 'idle' || agentState === 'listening' ? (
            <Wifi size={12} className="text-emerald-400" />
          ) : agentState === 'processing' || agentState === 'thinking' ? (
            <Zap size={12} className="text-amber-400 animate-pulse" />
          ) : agentState === 'speaking' ? (
            <Zap size={12} className="text-emerald-400" />
          ) : (
            <WifiOff size={12} className="text-red-400" />
          )}
          <span className="capitalize">{agentState || 'idle'}</span>
        </div>
        {activeToolCount > 0 && (
          <>
            <div className="h-3 w-px bg-white/[0.08]" />
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground animate-[tool-pulse_2s_ease-in-out_infinite]">
              <Zap size={10} className="text-amber-400" />
              {activeToolCount} tool{activeToolCount > 1 ? 's' : ''} active
            </div>
          </>
        )}
      </div>

      {/* Right: clients, theme, user */}
      <div className="flex items-center gap-3">
        <ClientStatusBar clients={clients} />
        <ThemeToggle />
        {user && <UserMenu user={user} onSignOut={signOut} />}
      </div>
    </header>
  );
}

