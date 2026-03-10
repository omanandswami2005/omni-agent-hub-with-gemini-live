/**
 * Page: MCPStorePage — Browse and manage MCP servers.
 */

import { useState, useEffect } from 'react';
import MCPStoreGrid from '@/components/mcp/MCPStoreGrid';
import MCPCategoryNav from '@/components/mcp/MCPCategoryNav';
import MCPDetail from '@/components/mcp/MCPDetail';
import { useMcpStore } from '@/stores/mcpStore';

export default function MCPStorePage() {
  const { catalog, loading, fetchCatalog, fetchEnabled, toggleMCP } = useMcpStore();
  const [category, setCategory] = useState('All');
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchCatalog();
    fetchEnabled();
  }, [fetchCatalog, fetchEnabled]);

  const filtered = catalog.filter((s) => {
    if (category !== 'All' && s.category !== category) return false;
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleToggle = async (mcpId, enabled) => {
    await toggleMCP(mcpId, enabled);
    // update selected detail if open
    if (selected?.id === mcpId) setSelected((prev) => ({ ...prev, enabled }));
  };

  if (selected) {
    return (
      <div className="mx-auto max-w-2xl py-6">
        <MCPDetail server={selected} onToggle={handleToggle} onClose={() => setSelected(null)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">MCP Store</h1>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search servers…"
          className="w-64 rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <MCPCategoryNav active={category} onChange={setCategory} />
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No servers found.</p>
      ) : (
        <MCPStoreGrid servers={filtered} onSelect={setSelected} />
      )}
    </div>
  );
}
