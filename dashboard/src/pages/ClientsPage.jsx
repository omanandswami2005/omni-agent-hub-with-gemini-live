/**
 * Page: ClientsPage — View and manage connected clients.
 */

import { useEffect } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import ClientList from '@/components/clients/ClientList';
import { useClientStore } from '@/stores/clientStore';

export default function ClientsPage() {
  useDocumentTitle('Connected Clients');
  const { clients, loading, fetchClients, watchClients, stopWatching } = useClientStore();

  useEffect(() => {
    fetchClients();
    const unsub = watchClients();
    return () => {
      unsub?.();
      stopWatching();
    };
  }, [fetchClients, watchClients, stopWatching]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Connected Clients</h1>
        <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
          {clients.length} client{clients.length !== 1 ? 's' : ''}
        </span>
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : clients.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No clients connected. Start the desktop client or Chrome extension to see them here.
        </p>
      ) : (
        <ClientList clients={clients} />
      )}
    </div>
  );
}
