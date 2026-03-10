/**
 * MCP: MCPDetail — Detailed view of a single MCP server.
 */

import MCPToggle from './MCPToggle';

export default function MCPDetail({ server, onToggle, onClose }) {
  if (!server) return null;

  return (
    <div className="space-y-4 rounded-lg border border-border p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{server.icon || '🔌'}</span>
          <div>
            <h2 className="text-lg font-medium">{server.name}</h2>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{server.category}</span>
          </div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">✕</button>
      </div>

      <p className="text-sm text-muted-foreground">{server.description}</p>

      {/* Enable / disable */}
      <div className="flex items-center justify-between rounded-lg bg-muted/50 p-3">
        <span className="text-sm font-medium">Enabled</span>
        <MCPToggle enabled={!!server.enabled} onChange={(val) => onToggle?.(server.id, val)} />
      </div>

      {/* Transport info */}
      {server.transport && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Transport</p>
          <p className="text-sm">{server.transport}{server.url ? ` — ${server.url}` : ''}</p>
        </div>
      )}

      {/* Tools list */}
      <div>
        <h3 className="mb-2 text-sm font-medium">Tools ({server.tools?.length || 0})</h3>
        {server.tools?.length > 0 ? (
          <ul className="space-y-1">
            {server.tools.map((tool, i) => (
              <li key={i} className="rounded bg-muted/50 px-3 py-1.5 text-sm">
                <span className="font-mono text-xs">{typeof tool === 'string' ? tool : tool.name}</span>
                {tool.description && <p className="text-xs text-muted-foreground">{tool.description}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">No tools listed</p>
        )}
      </div>
    </div>
  );
}
