/**
 * Layout: MobileSessionDrawer — Slide-up bottom sheet for session switching on mobile.
 * Triggered from MobileNav's Sessions tab (long press) or a swipe-up gesture.
 */

import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { X, Plus, MessageSquare, Trash2, Pencil } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useVoice } from '@/hooks/useVoiceProvider';
import { formatDistanceToNow } from 'date-fns';

export default function MobileSessionDrawer({ open, onClose }) {
    const navigate = useNavigate();
    const voice = useVoice();
    const sessions = useSessionStore((s) => s.sessions);
    const activeSessionId = useSessionStore((s) => s.activeSessionId);
    const switchSession = useSessionStore((s) => s.switchSession);
    const deleteSession = useSessionStore((s) => s.deleteSession);
    const renameSession = useSessionStore((s) => s.renameSession);
    const clearMessages = useChatStore((s) => s.clearMessages);

    const [search, setSearch] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [editTitle, setEditTitle] = useState('');
    const [confirmDeleteId, setConfirmDeleteId] = useState(null);
    const inputRef = useRef(null);
    const backdropRef = useRef(null);

    // Focus rename input
    useEffect(() => {
        if (editingId && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [editingId]);

    // Reset search when closed
    useEffect(() => {
        if (!open) {
            setSearch('');
            setEditingId(null);
            setConfirmDeleteId(null);
        }
    }, [open]);

    // Clear delete confirmation after timeout
    useEffect(() => {
        if (!confirmDeleteId) return;
        const t = setTimeout(() => setConfirmDeleteId(null), 3000);
        return () => clearTimeout(t);
    }, [confirmDeleteId]);

    const filtered = search
        ? sessions.filter((s) => (s.title || '').toLowerCase().includes(search.toLowerCase()))
        : sessions;

    const handleSelect = (session) => {
        if (session.id === activeSessionId) {
            onClose();
            return;
        }
        switchSession(session.id);
        clearMessages();
        navigate(`/session/${session.id}`);
        voice.reconnect?.();
        onClose();
    };

    const handleNewChat = () => {
        clearMessages();
        useSessionStore.getState().setActiveSession(null);
        useSessionStore.getState().setWantsNewSession(true);
        navigate('/');
        voice.reconnect?.();
        onClose();
    };

    const handleDelete = (e, session) => {
        e.stopPropagation();
        if (confirmDeleteId === session.id) {
            const wasActive = session.id === activeSessionId;
            deleteSession(session.id);
            setConfirmDeleteId(null);
            if (wasActive) {
                clearMessages();
                navigate('/');
                voice.reconnect?.();
            }
        } else {
            setConfirmDeleteId(session.id);
        }
    };

    const startRename = (e, session) => {
        e.stopPropagation();
        setEditTitle(session.title || '');
        setEditingId(session.id);
    };

    const commitRename = (session) => {
        const trimmed = editTitle.trim();
        if (trimmed && trimmed !== session.title) {
            renameSession(session.id, trimmed);
        }
        setEditingId(null);
    };

    const handleBackdropClick = (e) => {
        if (e.target === backdropRef.current) onClose();
    };

    if (!open) return null;

    return (
        <div
            ref={backdropRef}
            onClick={handleBackdropClick}
            className="fixed inset-0 z-50 flex items-end bg-black/40 backdrop-blur-sm animate-in fade-in duration-200"
        >
            <div className="w-full max-h-[75vh] rounded-t-2xl border-t border-border bg-background flex flex-col animate-in slide-in-from-bottom duration-300">
                {/* Handle bar */}
                <div className="flex justify-center pt-2 pb-1">
                    <div className="h-1 w-10 rounded-full bg-muted-foreground/30" />
                </div>

                {/* Header */}
                <div className="flex items-center justify-between px-4 pb-3">
                    <h2 className="text-base font-semibold">Sessions</h2>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleNewChat}
                            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
                        >
                            <Plus size={14} />
                            New Chat
                        </button>
                        <button
                            onClick={onClose}
                            className="rounded-lg p-1.5 hover:bg-muted transition-colors"
                            aria-label="Close"
                        >
                            <X size={18} />
                        </button>
                    </div>
                </div>

                {/* Search */}
                <div className="px-4 pb-3">
                    <input
                        type="text"
                        placeholder="Search sessions…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary placeholder:text-muted-foreground/60"
                    />
                </div>

                {/* Session list */}
                <div className="flex-1 overflow-y-auto px-4 pb-6 space-y-1">
                    {filtered.length === 0 ? (
                        <p className="py-8 text-center text-sm text-muted-foreground">
                            {search ? 'No sessions match.' : 'No sessions yet.'}
                        </p>
                    ) : (
                        filtered.map((s) => {
                            const timeAgo = s.created_at
                                ? formatDistanceToNow(new Date(s.created_at), { addSuffix: true })
                                : '';

                            return (
                                <div
                                    key={s.id}
                                    onClick={() => handleSelect(s)}
                                    className={cn(
                                        'flex w-full items-center gap-3 rounded-xl p-3 transition-colors cursor-pointer',
                                        s.id === activeSessionId
                                            ? 'bg-primary/10 border border-primary/20'
                                            : 'border border-transparent hover:bg-muted active:bg-muted',
                                    )}
                                >
                                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted">
                                        <MessageSquare size={16} className={s.id === activeSessionId ? 'text-primary' : 'text-muted-foreground'} />
                                    </div>

                                    <div className="min-w-0 flex-1">
                                        {editingId === s.id ? (
                                            <input
                                                ref={inputRef}
                                                value={editTitle}
                                                onChange={(e) => setEditTitle(e.target.value)}
                                                onBlur={() => commitRename(s)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') commitRename(s);
                                                    if (e.key === 'Escape') setEditingId(null);
                                                }}
                                                onClick={(e) => e.stopPropagation()}
                                                className="w-full rounded border border-border bg-background px-2 py-0.5 text-sm font-medium outline-none focus:ring-1 focus:ring-primary"
                                            />
                                        ) : (
                                            <>
                                                <p className="truncate text-sm font-medium">{s.title || 'Untitled'}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {s.message_count ?? 0} messages {timeAgo && `· ${timeAgo}`}
                                                </p>
                                            </>
                                        )}
                                    </div>

                                    {/* Actions — always visible on mobile (no hover) */}
                                    {editingId !== s.id && (
                                        <div className="flex shrink-0 items-center gap-1">
                                            <button
                                                onClick={(e) => startRename(e, s)}
                                                className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                                                aria-label="Rename"
                                            >
                                                <Pencil size={14} />
                                            </button>
                                            <button
                                                onClick={(e) => handleDelete(e, s)}
                                                className={cn(
                                                    'rounded-lg p-1.5 transition-colors',
                                                    confirmDeleteId === s.id
                                                        ? 'bg-destructive/10 text-destructive'
                                                        : 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
                                                )}
                                                aria-label={confirmDeleteId === s.id ? 'Confirm delete' : 'Delete'}
                                            >
                                                {confirmDeleteId === s.id ? (
                                                    <span className="text-xs font-medium">Delete?</span>
                                                ) : (
                                                    <Trash2 size={14} />
                                                )}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
}
