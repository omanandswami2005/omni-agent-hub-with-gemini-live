/**
 * Clients: ClientCard — Individual client connection card.
 */

import { Monitor, Globe, Smartphone, Glasses } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

const TYPE_ICONS = {
  desktop: Monitor,
  chrome: Globe,
  mobile: Smartphone,
  glasses: Glasses,
};

export default function ClientCard({ client }) {
  const Icon = TYPE_ICONS[client?.client_type] || Monitor;
  const connected = client?.connected ?? (client?.last_ping && (Date.now() - new Date(client.last_ping).getTime()) < 60_000);
  const lastSeen = client?.connected_at
    ? formatDistanceToNow(new Date(client.connected_at), { addSuffix: true })
    : client?.lastSeen || 'Unknown';

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Icon className="h-6 w-6 text-muted-foreground" />
          <div>
            <p className="font-medium">{client?.name || client?.client_type || 'Client'}</p>
            <p className="text-xs text-muted-foreground">{client?.client_id || client?.platform || ''}</p>
          </div>
        </div>
        <span
          className={`h-3 w-3 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`}
          title={connected ? 'Connected' : 'Disconnected'}
        />
      </div>
      <div className="mt-3 text-xs text-muted-foreground">
        <p>Connected: {lastSeen}</p>
        {client?.capabilities?.length > 0 && (
          <p>Capabilities: {client.capabilities.join(', ')}</p>
        )}
      </div>
    </div>
  );
}
