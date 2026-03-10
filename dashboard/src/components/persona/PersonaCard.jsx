/**
 * Persona: PersonaCard — Card display for a single persona.
 */

import { Pencil, Trash2 } from 'lucide-react';

export default function PersonaCard({ persona, onSelect, isActive = false, onEdit, onDelete }) {
  return (
    <div
      className={`group relative w-full rounded-lg border p-4 text-left transition-colors ${isActive ? 'border-primary bg-primary/10' : 'border-border hover:border-primary/50'
        }`}
    >
      <button onClick={() => onSelect?.(persona)} className="flex w-full items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
          {persona?.avatar_url ? (
            <img src={persona.avatar_url} alt="" className="h-10 w-10 rounded-full object-cover" />
          ) : (
            persona?.name?.[0] || '?'
          )}
        </div>
        <div className="min-w-0">
          <p className="font-medium">{persona?.name}</p>
          <p className="truncate text-sm text-muted-foreground">{persona?.voice || persona?.tagline}</p>
        </div>
      </button>

      {/* Edit / Delete (visible on hover) */}
      {(onEdit || onDelete) && (
        <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {onEdit && (
            <button
              onClick={(e) => { e.stopPropagation(); onEdit(persona); }}
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Edit persona"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(persona); }}
              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              aria-label="Delete persona"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
