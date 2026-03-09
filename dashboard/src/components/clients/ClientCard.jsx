/**
 * Clients: ClientCard — Individual client connection card.
 */

export default function ClientCard({ client }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{client?.icon || '💻'}</span>
          <div>
            <p className="font-medium">{client?.name || client?.type}</p>
            <p className="text-xs text-muted-foreground">{client?.platform}</p>
          </div>
        </div>
        <span
          className={`h-3 w-3 rounded-full ${client?.connected ? 'bg-green-500' : 'bg-red-500'}`}
        />
      </div>
      <div className="mt-3 text-xs text-muted-foreground">
        <p>Last seen: {client?.lastSeen || 'Never'}</p>
        <p>Capabilities: {client?.capabilities?.join(', ') || 'None'}</p>
      </div>
    </div>
  );
}
