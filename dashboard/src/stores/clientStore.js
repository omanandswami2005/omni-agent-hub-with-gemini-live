import { create } from 'zustand';
import { api } from '@/lib/api';
import { collection, onSnapshot } from 'firebase/firestore';
import { db } from '@/lib/firebase';

export const useClientStore = create((set) => ({
  clients: [],
  loading: false,
  _unsub: null,

  fetchClients: async () => {
    set({ loading: true });
    try {
      const clients = await api.get('/clients');
      set({ clients, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  watchClients: () => {
    const ref = collection(db, 'clients');
    const unsub = onSnapshot(ref, (snap) => {
      const clients = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
      set({ clients });
    });
    set({ _unsub: unsub });
    return unsub;
  },

  stopWatching: () => {
    set((state) => {
      state._unsub?.();
      return { _unsub: null };
    });
  },

  setClients: (clients) => set({ clients }),
}));
