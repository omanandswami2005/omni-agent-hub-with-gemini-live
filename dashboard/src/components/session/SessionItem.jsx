/**
 * Session: SessionItem — Single session row in the list.
 */

import { Trash2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

export default function SessionItem({ session, isActive, onSelect, onDelete }) {
  const timeAgo = session?.created_at
    ? formatDistanceToNow(new Date(session.created_at), { addSuffix: true })
    : session?.date || '';

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
            onClick={(e) => { e.stopPropagation(); onDelete(session); }}
            className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
            aria-label="Delete session"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}
