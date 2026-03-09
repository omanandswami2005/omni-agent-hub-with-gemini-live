import { create } from 'zustand';

export const useSessionStore = create((set) => ({
    sessions: [],
    activeSessionId: null,

    setSessions: (sessions) => set({ sessions }),
    setActiveSession: (id) => set({ activeSessionId: id }),
}));
