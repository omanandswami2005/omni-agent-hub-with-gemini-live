/**
 * MCP: MCPStoreGrid — Grid layout for MCP server cards.
 */

import MCPCard from './MCPCard';

export default function MCPStoreGrid({ servers = [], onSelect }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {servers.map((server) => (
        <MCPCard key={server.id} server={server} onSelect={onSelect} />
      ))}
    </div>
  );
}
