/**
 * Page: MCPStorePage — Browse and manage MCP servers.
 */

import { useState } from 'react';
import MCPStoreGrid from '@/components/mcp/MCPStoreGrid';
import MCPCategoryNav from '@/components/mcp/MCPCategoryNav';
import { useMcpStore } from '@/stores/mcpStore';

export default function MCPStorePage() {
  const { servers } = useMcpStore();
  const [category, setCategory] = useState('All');

  const filtered = category === 'All' ? servers : servers.filter((s) => s.category === category);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">MCP Store</h1>
      <MCPCategoryNav active={category} onChange={setCategory} />
      <MCPStoreGrid servers={filtered} />
    </div>
  );
}
