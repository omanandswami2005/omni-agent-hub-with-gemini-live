import { create } from 'zustand';
import { api } from '@/lib/api';

export const useSessionStore = create((set, get) => ({
    sessions: [],
    activeSessionId: null,
    loading: false,
    messagesLoading: false,
    error: null,

    loadSessions: async () => {
        set({ loading: true, error: null });
        try {
            const sessions = await api.get('/sessions');
            set({ sessions, loading: false });
        } catch (err) {
            set({ error: err.message, loading: false });
        }
    },

    loadMessages: async (sessionId) => {
        set({ messagesLoading: true });
        try {
            const messages = await api.get(`/sessions/${sessionId}/messages`);
            return messages || [];
        } catch {
            return [];
        } finally {
            set({ messagesLoading: false });
        }
    },

    createSession: async (data = {}) => {
        const session = await api.post('/sessions', data);
        set({ sessions: [session, ...get().sessions], activeSessionId: session.id });
        return session;
    },

    deleteSession: async (id) => {
        await api.delete(`/sessions/${id}`);
        set({
            sessions: get().sessions.filter((s) => s.id !== id),
            activeSessionId: get().activeSessionId === id ? null : get().activeSessionId,
        });
    },

    switchSession: (id) => set({ activeSessionId: id }),
    setSessions: (sessions) => set({ sessions }),
    setActiveSession: (id) => set({ activeSessionId: id }),

    /**
     * Ensure a session exists in the local list (fetch from API if missing).
     * Called when the WS creates a session server-side.
     */
    ensureSession: async (id) => {
        if (!id) return;
        const existing = get().sessions.find((s) => s.id === id);
        if (existing) return;
        try {
            const session = await api.get(`/sessions/${id}`);
            set({ sessions: [session, ...get().sessions] });
        } catch {
            // Session might not be ready yet — silently ignore
        }
    },
}));
