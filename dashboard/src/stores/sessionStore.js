import { create } from 'zustand';
import { api } from '@/lib/api';

export const useSessionStore = create((set, get) => ({
    sessions: [],
    activeSessionId: null,
    loading: false,
    error: null,

    loadSessions: async () => {
        set({ loading: true, error: null });
        try {
            const sessions = await api.get('/v1/sessions');
            set({ sessions, loading: false });
        } catch (err) {
            set({ error: err.message, loading: false });
        }
    },

    createSession: async (data = {}) => {
        const session = await api.post('/v1/sessions', data);
        set({ sessions: [session, ...get().sessions], activeSessionId: session.id });
        return session;
    },

    deleteSession: async (id) => {
        await api.delete(`/v1/sessions/${id}`);
        set({
            sessions: get().sessions.filter((s) => s.id !== id),
            activeSessionId: get().activeSessionId === id ? null : get().activeSessionId,
        });
    },

    switchSession: (id) => set({ activeSessionId: id }),
    setSessions: (sessions) => set({ sessions }),
    setActiveSession: (id) => set({ activeSessionId: id }),
}));
