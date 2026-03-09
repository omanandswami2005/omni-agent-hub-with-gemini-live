/**
 * Session: SessionList — List of past sessions with search.
 */

import SessionItem from './SessionItem';
import SessionSearch from './SessionSearch';

export default function SessionList({ sessions = [], onSelect }) {
  return (
    <div className="space-y-4">
      <SessionSearch />
      <div className="space-y-2">
        {sessions.map((session) => (
          <SessionItem key={session.id} session={session} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
