/**
 * Persona: PersonaCard — Card display for a single persona.
 */

export default function PersonaCard({ persona, onSelect, isActive = false }) {
  return (
    <button
      onClick={() => onSelect?.(persona)}
      className={`w-full rounded-lg border p-4 text-left transition-colors ${
        isActive ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
      }`}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground">
          {persona?.name?.[0] || '?'}
        </div>
        <div>
          <p className="font-medium">{persona?.name}</p>
          <p className="text-sm text-muted-foreground">{persona?.tagline}</p>
        </div>
      </div>
    </button>
  );
}
