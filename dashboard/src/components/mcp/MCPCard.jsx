/**
 * MCP: MCPCard — Individual MCP server card.
 */

import MCPIcon from './MCPIcon';

export default function MCPCard({ server, onSelect }) {
  const isOAuth = server?.kind === 'mcp_oauth';
  const isGoogleOAuth = server?.google_oauth_scopes?.length > 0;
  const isConnected = server?.state === 'connected';
  const needsOAuth = isOAuth || isGoogleOAuth;

  return (
    <button
      onClick={() => onSelect?.(server)}
      className="w-full rounded-lg border border-border p-4 text-left transition-colors hover:border-primary/50"
    >
      <div className="flex items-center gap-3">
        <MCPIcon icon={server?.icon} name={server?.name} size={28} />
        <div>
          <p className="font-medium">{server?.name}</p>
          <p className="text-xs text-muted-foreground">{server?.category}</p>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted-foreground">{server?.description}</p>
      <div className="mt-2 flex items-center gap-2">
        <span className="text-xs text-muted-foreground">
          {server?.tools_summary?.length || server?.tools?.length || 0} tools
        </span>
        {needsOAuth && isConnected && <span className="text-xs text-green-500">● Connected</span>}
        {needsOAuth && !isConnected && <span className="text-xs text-amber-500">{isGoogleOAuth ? 'Google Sign-in Required' : 'OAuth Required'}</span>}
        {!needsOAuth && (server?.state === 'enabled' || server?.state === 'connected') && <span className="text-xs text-green-500">Active</span>}
      </div>
    </button>
  );
}
