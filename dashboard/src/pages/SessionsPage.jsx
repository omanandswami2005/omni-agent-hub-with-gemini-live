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
  const { sessions, activeSessionId, loading, loadSessions, switchSession, deleteSession, createSession, renameSession } = useSessionStore();
  const clearMessages = useChatStore((s) => s.clearMessages);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleSelect = (session) => {
    switchSession(session.id);
    clearMessages?.();
    navigate(`/session/${session.id}`);
  };

  const handleDelete = async (session) => {
    const wasActive = session.id === activeSessionId;
    await deleteSession(session.id);
    if (wasActive) {
      clearMessages();
      navigate('/');
    }
  };

  const handleNewSession = async () => {
    try {
      const session = await createSession();
      clearMessages();
      switchSession(session.id);
      navigate(`/session/${session.id}`);
    } catch {
      // silently ignore
    }
  };

  const handleRename = async (session, title) => {
    await renameSession(session.id, title);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Sessions</h1>
        <button
          onClick={handleNewSession}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          New Session
        </button>
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={handleSelect}
          onDelete={handleDelete}
          onRename={handleRename}
        />
      )}
    </div>
  );
}
