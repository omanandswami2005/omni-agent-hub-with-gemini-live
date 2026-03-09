/**
 * Page: ClientsPage — View and manage connected clients.
 */

import ClientList from '@/components/clients/ClientList';
import { useClientStore } from '@/stores/clientStore';

export default function ClientsPage() {
  const { clients } = useClientStore();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Connected Clients</h1>
      <ClientList clients={clients} />
    </div>
  );
}
