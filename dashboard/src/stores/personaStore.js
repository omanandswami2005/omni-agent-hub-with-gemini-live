import { create } from 'zustand';
import { api } from '@/lib/api';

export const usePersonaStore = create((set, get) => ({
  personas: [],
  activePersona: null,
  loading: false,
  error: null,

  fetchPersonas: async () => {
    set({ loading: true, error: null });
    try {
      const personas = await api.get('/v1/personas');
      set({ personas, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  createPersona: async (data) => {
    const persona = await api.post('/v1/personas', data);
    set({ personas: [...get().personas, persona] });
    return persona;
  },

  updatePersona: async (id, data) => {
    const updated = await api.put(`/v1/personas/${id}`, data);
    set({
      personas: get().personas.map((p) => (p.id === id ? updated : p)),
      activePersona: get().activePersona?.id === id ? updated : get().activePersona,
    });
    return updated;
  },

  deletePersona: async (id) => {
    await api.delete(`/v1/personas/${id}`);
    set({
      personas: get().personas.filter((p) => p.id !== id),
      activePersona: get().activePersona?.id === id ? null : get().activePersona,
    });
  },

  setActivePersona: (persona) => set({ activePersona: persona }),
  setPersonas: (personas) => set({ personas }),
  setLoading: (loading) => set({ loading }),
}));
