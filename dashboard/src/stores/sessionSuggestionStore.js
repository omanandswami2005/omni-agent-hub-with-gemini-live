import { create } from 'zustand';

const AUTO_JOIN_KEY = 'omni_auto_join_session';

export const useSessionSuggestionStore = create((set) => ({
    /** The pending suggestion from the server, or null */
    suggestion: null,
    /** Whether the user has opted into auto-join (persisted in localStorage) */
    autoJoin: localStorage.getItem(AUTO_JOIN_KEY) === 'true',

    /** Called when server sends a session_suggestion message */
    setSuggestion: (suggestion) => set({ suggestion }),

    /** Dismiss the current suggestion */
    dismiss: () => set({ suggestion: null }),

    /** Enable auto-join for future sessions */
    enableAutoJoin: () => {
        localStorage.setItem(AUTO_JOIN_KEY, 'true');
        set({ autoJoin: true });
    },

    /** Disable auto-join */
    disableAutoJoin: () => {
        localStorage.removeItem(AUTO_JOIN_KEY);
        set({ autoJoin: false });
    },
}));
