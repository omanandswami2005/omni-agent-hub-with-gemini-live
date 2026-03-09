/**
 * MCP: MCPToggle — Enable/disable toggle for an MCP server.
 */

export default function MCPToggle({ enabled = false, onChange, label }) {
  return (
    <label className="flex cursor-pointer items-center gap-2">
      <div
        onClick={() => onChange?.(!enabled)}
        className={`relative h-6 w-11 rounded-full transition-colors ${
          enabled ? 'bg-primary' : 'bg-muted'
        }`}
      >
        <div
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
            enabled ? 'translate-x-5' : 'translate-x-0.5'
          }`}
        />
      </div>
      {label && <span className="text-sm">{label}</span>}
    </label>
  );
}
