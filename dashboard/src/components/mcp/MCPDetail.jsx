/**
 * MCP: MCPDetail — Detailed view of a single MCP server.
 */

// TODO: Implement:
//   - Server info (name, description, auth requirements)
//   - Tool list with descriptions
//   - Enable/disable toggle
//   - Connection status
//   - Configuration fields

export default function MCPDetail({ server, onToggle: _onToggle, onClose }) {
  return (
    <div className="space-y-4 rounded-lg border border-border p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">{server?.name}</h2>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
      </div>
      <p className="text-sm text-muted-foreground">{server?.description}</p>
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Tools ({server?.tools?.length || 0})</h3>
        {/* Tool list */}
      </div>
    </div>
  );
}
