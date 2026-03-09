import { create } from 'zustand';

export const usePersonaStore = create((set) => ({
  personas: [],
  activePersona: null,
  loading: false,

  setPersonas: (personas) => set({ personas }),
  setActivePersona: (persona) => set({ activePersona: persona }),
  setLoading: (loading) => set({ loading }),
}));
