/**
 * Page: PersonasPage — Manage AI personas.
 */

import PersonaList from '@/components/persona/PersonaList';
import { usePersonaStore } from '@/stores/personaStore';

export default function PersonasPage() {
  const { personas, activePersona, setActivePersona } = usePersonaStore();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Personas</h1>
        <button className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground">
          + New Persona
        </button>
      </div>
      <PersonaList
        personas={personas}
        activeId={activePersona?.id}
        onSelect={(p) => setActivePersona(p)}
      />
    </div>
  );
}
