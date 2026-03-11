/**
 * Clients: ClientCard — Individual client connection card.
 */

import { Monitor, Globe, Smartphone, Glasses, Laptop } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

const TYPE_META = {
  desktop: { icon: Laptop, label: 'Desktop App' },
  chrome: { icon: Globe, label: 'Chrome Extension' },
  mobile: { icon: Smartphone, label: 'Mobile' },
  glasses: { icon: Glasses, label: 'Smart Glasses' },
  web: { icon: Globe, label: 'Web Browser' },
};

export default function ClientCard({ client }) {
  const meta = TYPE_META[client?.client_type] ?? TYPE_META.web;
  const Icon = meta.icon;
  const connected = client?.connected ?? true;
  const lastSeen = client?.connected_at
    ? formatDistanceToNow(new Date(client.connected_at), { addSuffix: true })
    : client?.lastSeen || 'Unknown';

  const osLabel = client?.os_name && client.os_name !== 'Unknown' ? client.os_name : null;

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
            <Icon className="h-5 w-5 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">{meta.label}</p>
            {osLabel && (
              <p className="text-xs text-muted-foreground">{osLabel}</p>
            )}
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
