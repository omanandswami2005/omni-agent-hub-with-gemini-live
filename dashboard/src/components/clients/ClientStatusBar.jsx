/**
 * Clients: ClientStatusBar — Connected clients status indicator.
 */

export default function ClientStatusBar({ clients = [] }) {
  return (
    <div className="flex items-center gap-3">
      {clients.map((client) => (
        <div key={client.client_id || client.client_type} className="flex items-center gap-1.5" title={client.os_name || client.client_type}>
          <span
            className={`h-2 w-2 rounded-full ${client.connected ? 'bg-green-500' : 'bg-muted-foreground'
              }`}
          />
          <span className="text-xs text-muted-foreground">{client.client_type}</span>
        </div>
      ))}
    </div>
  );
}
