/**
 * Clients: ClientList — List of all connected/registered clients.
 */

import ClientCard from './ClientCard';

export default function ClientList({ clients = [] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {clients.map((client) => (
        <ClientCard key={client.id} client={client} />
      ))}
    </div>
  );
}
