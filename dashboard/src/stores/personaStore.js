import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { api } from '@/lib/api';

export const usePersonaStore = create(
  persist(
    (set, get) => ({
      personas: [],
      activePersona: null,
      loading: false,
      error: null,

      fetchPersonas: async () => {
        set({ loading: true, error: null });
        try {
          const personas = await api.get('/personas');
          set({ personas, loading: false });
          // If no active persona set, default to the first one
          if (!get().activePersona && personas.length > 0) {
            set({ activePersona: personas[0] });
          }
        } catch (err) {
          set({ error: err.message, loading: false });
        }
      },

      createPersona: async (data) => {
        const persona = await api.post('/personas', data);
        set({ personas: [...get().personas, persona] });
        return persona;
      },

      updatePersona: async (id, data) => {
        const updated = await api.put(`/personas/${id}`, data);
        set({
          personas: get().personas.map((p) => (p.id === id ? updated : p)),
          activePersona: get().activePersona?.id === id ? updated : get().activePersona,
        });
        return updated;
      },

      deletePersona: async (id) => {
        await api.delete(`/personas/${id}`);
        set({
          personas: get().personas.filter((p) => p.id !== id),
          activePersona: get().activePersona?.id === id ? null : get().activePersona,
        });
      },

      setActivePersona: (persona) => set({ activePersona: persona }),
      setPersonas: (personas) => set({ personas }),
      setLoading: (loading) => set({ loading }),
    }),
    {
      name: 'omni-persona',
      partialize: (state) => ({ activePersona: state.activePersona }),
    },
  ),
);
