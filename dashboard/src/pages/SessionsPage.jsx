/**
 * Page: SessionsPage — View past conversation sessions.
 */

import SessionList from '@/components/session/SessionList';
import { useSessionStore } from '@/stores/sessionStore';

export default function SessionsPage() {
  const { sessions } = useSessionStore();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sessions</h1>
      <SessionList sessions={sessions} />
    </div>
  );
}
