import { create } from 'zustand';
import { api } from '@/lib/api';

export const useSessionStore = create((set, get) => ({
    sessions: [],
    activeSessionId: null,
    loading: false,
    messagesLoading: false,
    error: null,
    // Flag to indicate user explicitly wants a new session
    wantsNewSession: false,

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
        const remaining = get().sessions.filter((s) => s.id !== id);
        const wasActive = get().activeSessionId === id;
        set({
            sessions: remaining,
            activeSessionId: wasActive ? (remaining[0]?.id ?? null) : get().activeSessionId,
        });
    },

    renameSession: async (id, title) => {
        const updated = await api.put(`/sessions/${id}`, { title });
        set({
            sessions: get().sessions.map((s) =>
                s.id === id ? { ...s, title: updated.title ?? title } : s,
            ),
        });
        return updated;
    },

    switchSession: (id) => set({ activeSessionId: id }),
    setSessions: (sessions) => set({ sessions }),
    setActiveSession: (id) => set({ activeSessionId: id }),
    setWantsNewSession: (val) => set({ wantsNewSession: val }),

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
