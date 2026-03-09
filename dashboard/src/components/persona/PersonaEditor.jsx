/**
 * Persona: PersonaEditor — Create/edit persona configuration.
 */

// TODO: Implement:
//   - Name, tagline, system instruction fields
//   - Voice selection dropdown (Puck, Charon, Kore, etc.)
//   - MCP server selection (multi-select)
//   - Tool permission toggles
//   - Preview before save

export default function PersonaEditor({ persona, onSave, onCancel }) {
  return (
    <div className="space-y-4 rounded-lg border border-border p-6">
      <h2 className="text-lg font-medium">{persona ? 'Edit Persona' : 'Create Persona'}</h2>
      {/* Form fields */}
      <div className="flex gap-2">
        <button onClick={onCancel} className="rounded-lg border border-border px-4 py-2 text-sm">
          Cancel
        </button>
        <button onClick={() => onSave?.({})} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground">
          Save
        </button>
      </div>
    </div>
  );
}
