/**
 * Session: SessionList — List of past sessions with search.
 */

import { useState } from 'react';
import SessionItem from './SessionItem';
import SessionSearch from './SessionSearch';

export default function SessionList({ sessions = [], activeId, onSelect, onDelete, onRename }) {
  const [search, setSearch] = useState('');

  const filtered = search
    ? sessions.filter((s) => (s.title || '').toLowerCase().includes(search.toLowerCase()))
    : sessions;

  return (
    <div className="space-y-4">
      <SessionSearch value={search} onChange={setSearch} />
      {filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {search ? 'No sessions match your search.' : 'No sessions yet.'}
        </p>
      ) : (
        <div className="space-y-2">
          {filtered.map((session) => (
            <SessionItem
              key={session.id}
              session={session}
              isActive={session.id === activeId}
              onSelect={onSelect}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))}
        </div>
      )}
    </div>
  );
}
