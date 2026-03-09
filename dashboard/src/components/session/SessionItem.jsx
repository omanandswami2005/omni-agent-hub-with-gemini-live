/**
 * Session: SessionItem — Single session row in the list.
 */

export default function SessionItem({ session, onSelect }) {
  return (
    <button
      onClick={() => onSelect?.(session)}
      className="flex w-full items-center justify-between rounded-lg border border-border p-3 text-left hover:bg-muted"
    >
      <div>
        <p className="text-sm font-medium">{session?.title || 'Untitled Session'}</p>
        <p className="text-xs text-muted-foreground">
          {session?.persona} · {session?.messageCount} messages
        </p>
      </div>
      <span className="text-xs text-muted-foreground">{session?.date}</span>
    </button>
  );
}
