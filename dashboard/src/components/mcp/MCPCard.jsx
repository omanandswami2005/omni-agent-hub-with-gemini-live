/**
 * MCP: MCPCard — Individual MCP server card.
 */

export default function MCPCard({ server, onSelect }) {
  return (
    <button
      onClick={() => onSelect?.(server)}
      className="w-full rounded-lg border border-border p-4 text-left transition-colors hover:border-primary/50"
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{server?.icon || '🔌'}</span>
        <div>
          <p className="font-medium">{server?.name}</p>
          <p className="text-xs text-muted-foreground">{server?.category}</p>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{server?.description}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground">{server?.tools?.length || 0} tools</span>
        {server?.enabled && <span className="text-xs text-green-500">Active</span>}
      </div>
    </button>
  );
}
