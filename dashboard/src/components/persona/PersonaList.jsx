/**
 * Persona: PersonaList — Grid/list of available personas.
 */

import PersonaCard from './PersonaCard';

export default function PersonaList({ personas = [], activeId, onSelect }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {personas.map((p) => (
        <PersonaCard
          key={p.id}
          persona={p}
          isActive={p.id === activeId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
