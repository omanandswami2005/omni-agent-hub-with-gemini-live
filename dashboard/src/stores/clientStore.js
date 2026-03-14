import { create } from 'zustand';
import { api } from '@/lib/api';

export const useClientStore = create((set) => ({
  clients: [],
  loading: false,
  // Which client_type currently holds the mic floor (null = nobody)
  micFloorHolder: null,

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
  setMicFloorHolder: (holder) => set({ micFloorHolder: holder }),
}));
