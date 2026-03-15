/**
 * Page: MCPStorePage — Browse and manage MCP servers.
 */

import { useState, useEffect } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import MCPStoreGrid from '@/components/mcp/MCPStoreGrid';
import MCPDetail from '@/components/mcp/MCPDetail';
import { useMcpStore } from '@/stores/mcpStore';

export default function MCPStorePage() {
  useDocumentTitle('MCP & Plugins');
  const { catalog, loading, error, fetchCatalog, fetchEnabled, toggleMCP } = useMcpStore();
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchCatalog();
    fetchEnabled();
  }, [fetchCatalog, fetchEnabled]);

  const filtered = catalog.filter((s) => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleToggle = async (mcpId, enabled) => {
    try {
      await toggleMCP(mcpId, enabled);
      if (selected?.id === mcpId) setSelected((prev) => ({ ...prev, state: enabled ? 'enabled' : 'available' }));
    } catch {
      // Re-fetch catalog to reset UI state after failed toggle
      fetchCatalog();
    }
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
        <h1 className="text-2xl font-bold">MCP &amp; Plugins</h1>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          className="w-64 rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
          {error}
        </div>
      )}
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
