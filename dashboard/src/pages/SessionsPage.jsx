/**
 * Page: SessionsPage — View past conversation sessions.
 */

import { useEffect } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import SessionList from '@/components/session/SessionList';
import { useSessionStore } from '@/stores/sessionStore';

export default function SessionsPage() {
  useDocumentTitle('Sessions');
  const { sessions, activeSessionId, loading, loadSessions, switchSession, deleteSession } = useSessionStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sessions</h1>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={(s) => switchSession(s.id)}
          onDelete={(s) => deleteSession(s.id)}
        />
      )}
    </div>
  );
}
