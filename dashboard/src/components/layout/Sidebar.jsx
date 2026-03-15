/**
 * Layout: Sidebar — Navigation sidebar with collapsible session list.
 */

import { useState, useRef, useEffect } from 'react';
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
  Pencil,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { useUiStore } from '@/stores/uiStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';
import { useVoice } from '@/hooks/useVoiceProvider';
import KeyboardShortcut from '@/components/shared/KeyboardShortcut';
import ConfirmDialog from '@/components/shared/ConfirmDialog';
import { formatDistanceToNow } from 'date-fns';

/** Modal for renaming a session (shown over the sidebar) */
function RenameSessionModal({ session, onConfirm, onCancel }) {
  const [value, setValue] = useState(session?.title || '');
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') submit();
    if (e.key === 'Escape') onCancel();
  };

  const submit = () => {
    const trimmed = value.trim();
    if (trimmed) onConfirm(trimmed);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-sm rounded-lg border border-border bg-background p-5 shadow-xl">
        <h3 className="text-base font-semibold">Rename session</h3>
        <p className="mt-1 mb-3 text-xs text-muted-foreground truncate">
          "{session?.title || 'Untitled'}"
        </p>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="New name…"
          className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!value.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            Rename
          </button>
        </div>
      </div>
    </div>
  );
}

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: Home, shortcut: ['1'] },
  { to: '/personas', label: 'Personas', icon: Users, shortcut: ['2'] },
  { to: '/mcp-store', label: 'MCP & Plugins', icon: Store, shortcut: ['3'] },
  { id: 'sessions', to: '/sessions', label: 'Sessions', icon: Clock, shortcut: ['4'], hasSublist: true },
  { to: '/clients', label: 'Clients', icon: Monitor, shortcut: ['5'] },
  { to: '/gallery', label: 'Gallery', icon: ImageIcon, shortcut: ['6'] },
  { to: '/settings', label: 'Settings', icon: Settings, shortcut: ['7'] },
];

function SidebarSessionList() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const switchSession = useSessionStore((s) => s.switchSession);
  const renameSession = useSessionStore((s) => s.renameSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const navigate = useNavigate();
  const voice = useVoice();

  // Modal state
  const [renameTarget, setRenameTarget] = useState(null);   // session object
  const [deleteTarget, setDeleteTarget] = useState(null);   // session object

  const recent = sessions.slice(0, 25);

  const handleClick = (session) => {
    if (session.id === activeSessionId) return;
    switchSession(session.id);
    clearMessages();
    navigate(`/session/${session.id}`);
    voice.reconnect?.();
  };

  const handleConfirmRename = (newTitle) => {
    if (renameTarget) renameSession(renameTarget.id, newTitle);
    setRenameTarget(null);
  };

  const handleConfirmDelete = () => {
    if (!deleteTarget) return;
    const wasActive = deleteTarget.id === activeSessionId;
    deleteSession(deleteTarget.id);
    setDeleteTarget(null);
    if (wasActive) {
      clearMessages();
      navigate('/dashboard');
      voice.reconnect?.();
    }
  };

  if (recent.length === 0) {
    return (
      <p className="px-3 py-2 text-[11px] text-muted-foreground">No sessions yet</p>
    );
  }

  return (
    <>
      <div className="max-h-[40vh] space-y-0.5 overflow-y-auto scrollbar-thin">
        {recent.map((s) => (
          <div
            key={s.id}
            className={cn(
              'group flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors cursor-pointer',
              s.id === activeSessionId
                ? 'bg-primary/10 text-primary font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
            )}
            onClick={() => handleClick(s)}
          >
            <MessageSquare size={12} className="shrink-0" />
            <span className="min-w-0 flex-1 truncate">{s.title || 'Untitled'}</span>

            {/* Action icons – visible on active, revealed on hover for others */}
            <div className={cn(
              'flex shrink-0 items-center gap-0.5 transition-opacity',
              s.id === activeSessionId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
            )}>
              <button
                onClick={(e) => { e.stopPropagation(); setRenameTarget(s); }}
                className="rounded p-0.5 hover:bg-primary/10 hover:text-primary"
                title="Rename session"
              >
                <Pencil size={11} />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setDeleteTarget(s); }}
                className="rounded p-0.5 hover:bg-destructive/10 hover:text-destructive"
                title="Delete session"
              >
                <Trash2 size={11} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {sessions.length > 25 && (
        <button
          onClick={() => navigate('/sessions')}
          className="w-full px-3 py-1.5 text-[11px] text-primary hover:underline text-left"
        >
          View all {sessions.length} sessions →
        </button>
      )}

      {/* Rename modal */}
      {renameTarget && (
        <RenameSessionModal
          session={renameTarget}
          onConfirm={handleConfirmRename}
          onCancel={() => setRenameTarget(null)}
        />
      )}

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete session?"
        message={`"${deleteTarget?.title || 'Untitled'}" will be permanently deleted.`}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
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
  const connectedClients = useClientStore((s) => s.clients);

  const handleNewChat = () => {
    clearMessages();
    useSessionStore.getState().setActiveSession(null);
    useSessionStore.getState().setWantsNewSession(true);
    navigate('/dashboard');
    voice.reconnect?.();
  };

  return (
    <aside
      className={cn(
        'hidden flex-col bg-[var(--sidebar)] text-[var(--sidebar-foreground)] transition-all duration-200 md:flex',
        sidebarOpen ? 'w-60' : 'w-16',
      )}
    >
      {/* Logo + New Chat */}
      <div className="flex h-14 items-center justify-between px-4">
        {sidebarOpen && (
          <span className="text-base font-semibold tracking-tight">Omni</span>
        )}
        <div className="flex items-center gap-1">
          {sidebarOpen && (
            <button
              onClick={handleNewChat}
              className="rounded-lg p-1.5 transition-colors hover:bg-white/5"
              aria-label="New chat"
              title="New chat"
            >
              <Plus size={16} />
            </button>
          )}
          <button
            onClick={toggleSidebar}
            className="rounded-lg p-1.5 transition-colors hover:bg-white/5"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeft size={16} />}
          </button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, shortcut, hasSublist }) => {
          const isActive = to === '/dashboard'
            ? location.pathname === '/dashboard' || location.pathname.startsWith('/session/')
            : location.pathname.startsWith(to);

          if (hasSublist && sidebarOpen) {
            return (
              <div key={to}>
                <button
                  className={cn(
                    'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-white/8 text-foreground font-medium'
                      : 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
                  )}
                  title={label}
                  onClick={() => {
                    setSessionsExpanded((prev) => !prev);
                    navigate(to);
                  }}
                >
                  <Icon size={16} className="shrink-0" />
                  <span className="flex-1 text-left">{label}</span>
                  <ChevronDown size={14} className={cn(
                    'transition-transform duration-200',
                    !sessionsExpanded && '-rotate-90',
                  )} />
                </button>
                {sessionsExpanded && (
                  <div className="ml-3 mt-1 border-l border-border/40 pl-2">
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
                  ? 'bg-white/8 text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
              )}
              title={label}
            >
              <Icon size={16} className="shrink-0" />
              {sidebarOpen && <span className="flex-1">{label}</span>}
              {to === '/clients' && connectedClients.length > 0 && (
                <span className="flex items-center gap-0.5">
                  {connectedClients.slice(0, 3).map((c, i) => (
                    <span key={c.client_id || i} className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  ))}
                  {connectedClients.length > 3 && (
                    <span className="text-[9px] text-muted-foreground">+{connectedClients.length - 3}</span>
                  )}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Active persona indicator */}
      {sidebarOpen && activePersona && (
        <div className="border-t border-border/40 p-3">
          <div className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-foreground text-xs font-medium text-background">
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
