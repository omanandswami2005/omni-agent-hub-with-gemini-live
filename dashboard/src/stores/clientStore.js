import { create } from 'zustand';
import { api } from '@/lib/api';

export const useClientStore = create((set) => ({
  clients: [],
  loading: false,

  fetchClients: async () => {
    set({ loading: true });
    try {
      const clients = await api.get('/clients');
      set({ clients, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setClients: (clients) => set({ clients }),
}));
