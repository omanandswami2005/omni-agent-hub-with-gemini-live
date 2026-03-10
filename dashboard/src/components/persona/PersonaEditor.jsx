/**
 * Persona: PersonaEditor — Create/edit persona configuration.
 */

import { useState, useEffect } from 'react';
import VoicePreview from '@/components/persona/VoicePreview';

const EMPTY_FORM = {
  name: '',
  voice: 'Kore',
  system_instruction: '',
  mcp_ids: [],
  avatar_url: '',
};

export default function PersonaEditor({ persona, onSave, onCancel, mcpCatalog = [] }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (persona) {
      setForm({
        name: persona.name || '',
        voice: persona.voice || 'Kore',
        system_instruction: persona.system_instruction || '',
        mcp_ids: persona.mcp_ids || [],
        avatar_url: persona.avatar_url || '',
      });
    } else {
      setForm(EMPTY_FORM);
    }
  }, [persona]);

  const update = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const toggleMcp = (id) => {
    setForm((prev) => ({
      ...prev,
      mcp_ids: prev.mcp_ids.includes(id) ? prev.mcp_ids.filter((m) => m !== id) : [...prev.mcp_ids, id],
    }));
  };

  const validate = () => {
    const errs = {};
    if (!form.name.trim()) errs.name = 'Name is required';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = () => {
    if (validate()) onSave?.(form);
  };

  return (
    <div className="space-y-5 rounded-lg border border-border p-6">
      <h2 className="text-lg font-medium">{persona ? 'Edit Persona' : 'Create Persona'}</h2>

      {/* Name */}
      <div>
        <label className="mb-1 block text-sm font-medium">Name *</label>
        <input
          value={form.name}
          onChange={(e) => update('name', e.target.value)}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="e.g. Atlas, Nova, Sage…"
        />
        {errors.name && <p className="mt-1 text-xs text-destructive">{errors.name}</p>}
      </div>

      {/* Avatar URL */}
      <div>
        <label className="mb-1 block text-sm font-medium">Avatar URL</label>
        <input
          value={form.avatar_url}
          onChange={(e) => update('avatar_url', e.target.value)}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="https://…"
        />
      </div>

      {/* Voice selection */}
      <div>
        <label className="mb-1 block text-sm font-medium">Voice</label>
        <VoicePreview selected={form.voice} onSelect={(v) => update('voice', v)} />
      </div>

      {/* System instruction */}
      <div>
        <label className="mb-1 block text-sm font-medium">System Instruction</label>
        <textarea
          value={form.system_instruction}
          onChange={(e) => update('system_instruction', e.target.value)}
          rows={4}
          className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="You are a helpful assistant that…"
        />
      </div>

      {/* MCP server selection */}
      {mcpCatalog.length > 0 && (
        <div>
          <label className="mb-1 block text-sm font-medium">MCP Servers</label>
          <div className="flex flex-wrap gap-2">
            {mcpCatalog.map((mcp) => (
              <button
                key={mcp.id}
                onClick={() => toggleMcp(mcp.id)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${form.mcp_ids.includes(mcp.id)
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:border-primary/50'
                  }`}
              >
                {mcp.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-2">
        <button onClick={onCancel} className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-muted">
          Cancel
        </button>
        <button onClick={handleSave} className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
          {persona ? 'Update' : 'Create'}
        </button>
      </div>
    </div>
  );
}
