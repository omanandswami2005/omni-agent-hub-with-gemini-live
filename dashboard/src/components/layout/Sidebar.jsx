/**
 * Layout: Sidebar — Navigation sidebar with collapsible session list.
 */

import { useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router';
import {
  Home,
  Users,
  Store,
  Clock,
  Monitor,
  Image as ImageIcon,
  Settings,
  PanelLeftClose,
  PanelLeft,
  ChevronDown,
  ChevronRight,
  Plus,
  MessageSquare,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useUiStore } from '@/stores/uiStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useVoice } from '@/hooks/useVoiceProvider';
import KeyboardShortcut from '@/components/shared/KeyboardShortcut';
import { formatDistanceToNow } from 'date-fns';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: Home, shortcut: ['1'] },
  { to: '/personas', label: 'Personas', icon: Users, shortcut: ['2'] },
  { to: '/mcp-store', label: 'MCP Store', icon: Store, shortcut: ['3'] },
  { id: 'sessions', to: '/sessions', label: 'Sessions', icon: Clock, shortcut: ['4'], hasSublist: true },
  { to: '/clients', label: 'Clients', icon: Monitor, shortcut: ['5'] },
  { to: '/gallery', label: 'Gallery', icon: ImageIcon, shortcut: ['6'] },
  { to: '/settings', label: 'Settings', icon: Settings, shortcut: ['7'] },
];

function SidebarSessionList() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const switchSession = useSessionStore((s) => s.switchSession);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const navigate = useNavigate();
  const voice = useVoice();

  const recent = sessions.slice(0, 10);

  const handleClick = (session) => {
    if (session.id === activeSessionId) return; // already on this session
    switchSession(session.id);
    clearMessages();
    navigate(`/session/${session.id}`);
    // Reconnect WS so server binds to this session
    voice.reconnect?.();
  };

  if (recent.length === 0) {
    return (
      <p className="px-3 py-2 text-[11px] text-muted-foreground">No sessions yet</p>
    );
  }

  return (
    <div className="max-h-48 space-y-0.5 overflow-y-auto">
      {recent.map((s) => (
        <button
          key={s.id}
          onClick={() => handleClick(s)}
          className={cn(
            'flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-xs transition-colors',
            s.id === activeSessionId
              ? 'bg-primary/10 text-primary font-medium'
              : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
          )}
          title={s.title || 'Untitled Session'}
        >
          <MessageSquare size={12} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate">{s.title || 'Untitled'}</span>
          <span className="shrink-0 text-[10px] opacity-60">
            {s.created_at ? formatDistanceToNow(new Date(s.created_at), { addSuffix: false }) : ''}
          </span>
        </button>
      ))}
    </div>
  );
}

export default function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUiStore();
  const { activePersona } = usePersonaStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [sessionsExpanded, setSessionsExpanded] = useState(false);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const voice = useVoice();

  const handleNewChat = () => {
    clearMessages();
    useSessionStore.getState().setActiveSession(null);
    navigate('/');
    // Reconnect WS so server creates a fresh session
    voice.reconnect?.();
  };

  return (
    <aside
      className={cn(
        'hidden flex-col border-r border-border bg-[var(--sidebar)] text-[var(--sidebar-foreground)] transition-all duration-200 md:flex',
        sidebarOpen ? 'w-64' : 'w-16',
      )}
    >
      {/* Logo + New Chat */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        {sidebarOpen && <span className="text-lg font-bold">Omni</span>}
        <div className="flex items-center gap-1">
          {sidebarOpen && (
            <button
              onClick={handleNewChat}
              className="rounded-md p-1.5 hover:bg-accent"
              aria-label="New chat"
              title="New chat"
            >
              <Plus size={18} />
            </button>
          )}
          <button
            onClick={toggleSidebar}
            className="rounded-md p-1.5 hover:bg-accent"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
          </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, shortcut, hasSublist }) => {
          const isActive = to === '/'
            ? location.pathname === '/' || location.pathname.startsWith('/session/')
            : location.pathname.startsWith(to);

          if (hasSublist && sidebarOpen) {
            // Sessions with collapsible sublist
            return (
              <div
                key={to}
                onMouseEnter={() => setSessionsExpanded(true)}
                onMouseLeave={() => setSessionsExpanded(false)}
              >
                <button
                  onClick={() => setSessionsExpanded((prev) => !prev)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-accent text-accent-foreground font-medium'
                      : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                  )}
                  title={label}
                >
                  <Icon size={18} />
                  <span className="flex-1 text-left">{label}</span>
                  {sessionsExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
                {sessionsExpanded && (
                  <div className="ml-2 mt-1 border-l border-border pl-2">
                    <SidebarSessionList />
                  </div>
                )}
              </div>
            );
          }

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
