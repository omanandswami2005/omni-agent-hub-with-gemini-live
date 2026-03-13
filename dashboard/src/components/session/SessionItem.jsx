/**
 * Session: SessionItem — Single session row in the list.
 */

import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

export default function SessionItem({ session, isActive, onSelect, onDelete }) {
  const [confirming, setConfirming] = useState(false);
  const timeAgo = session?.created_at
    ? formatDistanceToNow(new Date(session.created_at), { addSuffix: true })
    : session?.date || '';

  const handleDelete = (e) => {
    e.stopPropagation();
    if (confirming) {
      onDelete(session);
      setConfirming(false);
    } else {
      setConfirming(true);
      // Auto-cancel after 3 seconds
      setTimeout(() => setConfirming(false), 3000);
    }
  };

  return (
    <div
      className={`group flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors ${isActive ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted'
        }`}
    >
      <button onClick={() => onSelect?.(session)} className="min-w-0 flex-1 text-left">
        <p className="truncate text-sm font-medium">{session?.title || 'Untitled Session'}</p>
        <p className="text-xs text-muted-foreground">
          {session?.persona_id || session?.persona} · {session?.message_count ?? session?.messageCount ?? 0} messages
        </p>
      </button>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">{timeAgo}</span>
        {onDelete && (
          <button
            onClick={handleDelete}
            className={`rounded px-1.5 py-1 text-xs transition-all ${confirming
              ? 'bg-destructive/10 text-destructive opacity-100'
              : 'text-muted-foreground opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100'
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
