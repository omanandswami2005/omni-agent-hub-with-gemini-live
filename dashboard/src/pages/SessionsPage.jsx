/**
 * Page: SessionsPage — View past conversation sessions.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import SessionList from '@/components/session/SessionList';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';

export default function SessionsPage() {
  useDocumentTitle('Sessions');
  const navigate = useNavigate();
  const { sessions, activeSessionId, loading, loadSessions, switchSession, deleteSession } = useSessionStore();
  const clearMessages = useChatStore((s) => s.clearMessages);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleSelect = (session) => {
    switchSession(session.id);
    // Clear current chat and navigate to dashboard to start/resume session
    clearMessages?.();
    navigate('/');
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sessions</h1>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={handleSelect}
          onDelete={(s) => deleteSession(s.id)}
        />
      )}
    </div>
  );
}
