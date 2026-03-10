/**
 * Page: PersonasPage — Manage AI personas.
 */

import { useState, useEffect } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import PersonaList from '@/components/persona/PersonaList';
import PersonaEditor from '@/components/persona/PersonaEditor';
import { usePersonaStore } from '@/stores/personaStore';
import { useMcpStore } from '@/stores/mcpStore';

export default function PersonasPage() {
  useDocumentTitle('Personas');
  const { personas, activePersona, setActivePersona, fetchPersonas, createPersona, updatePersona, deletePersona, loading } = usePersonaStore();
  const mcpCatalog = useMcpStore((s) => s.catalog);
  const [editing, setEditing] = useState(null); // null = closed, undefined = new, persona = edit

  useEffect(() => {
    fetchPersonas();
  }, [fetchPersonas]);

  const handleSave = async (form) => {
    if (editing?.id) {
      await updatePersona(editing.id, form);
    } else {
      await createPersona(form);
    }
    setEditing(null);
  };

  const handleDelete = async (persona) => {
    await deletePersona(persona.id);
  };

  if (editing !== null) {
    return (
      <div className="mx-auto max-w-2xl py-6">
        <PersonaEditor
          persona={editing || undefined}
          mcpCatalog={mcpCatalog}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Personas</h1>
        <button
          onClick={() => setEditing(undefined)}
          className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          + New Persona
        </button>
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : personas.length === 0 ? (
        <p className="text-sm text-muted-foreground">No personas yet. Create one to get started.</p>
      ) : (
        <PersonaList
          personas={personas}
          activeId={activePersona?.id}
          onSelect={(p) => setActivePersona(p)}
          onEdit={(p) => setEditing(p)}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}
