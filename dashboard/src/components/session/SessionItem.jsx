/**
 * Session: SessionItem — Single session row in the list.
 */

import { useState, useRef, useEffect } from 'react';
import { Trash2, Pencil } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

export default function SessionItem({ session, isActive, onSelect, onDelete, onRename }) {
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const inputRef = useRef(null);
  const timeAgo = session?.created_at
    ? formatDistanceToNow(new Date(session.created_at), { addSuffix: true })
    : session?.date || '';

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const handleDelete = (e) => {
    e.stopPropagation();
    if (confirming) {
      onDelete(session);
      setConfirming(false);
    } else {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000);
    }
  };

  const startRename = (e) => {
    e.stopPropagation();
    setEditTitle(session?.title || '');
    setEditing(true);
  };

  const commitRename = () => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== session?.title) {
      onRename?.(session, trimmed);
    }
    setEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') commitRename();
    if (e.key === 'Escape') setEditing(false);
  };

  return (
    <div
      className={`group flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors cursor-pointer ${isActive ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted'
        }`}
      onClick={() => onSelect?.(session)}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          onClick={(e) => e.stopPropagation()}
          className="w-full rounded border border-border bg-background px-1.5 py-0.5 text-sm font-medium outline-none focus:ring-1 focus:ring-primary"
        />
      ) : (
        <div className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-medium">{session?.title || 'Untitled Session'}</p>
          <p className="text-xs text-muted-foreground">
            {session?.persona_id || session?.persona} · {session?.message_count ?? session?.messageCount ?? 0} messages
          </p>
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">{timeAgo}</span>
        {/* Always show buttons on all devices - ensure visibility */}
        {onRename && !editing && (
          <button
            onClick={startRename}
            className="rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground opacity-100"
            aria-label="Rename session"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {onDelete && (
          <button
            onClick={handleDelete}
            className={`rounded px-1.5 py-1 text-xs transition-all ${confirming
              ? 'bg-destructive/10 text-destructive opacity-100'
              : 'text-muted-foreground opacity-100 hover:bg-destructive/10 hover:text-destructive'
              }`}
            aria-label={confirming ? 'Confirm delete' : 'Delete session'}
          >
            {confirming ? 'Delete?' : <Trash2 className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}
