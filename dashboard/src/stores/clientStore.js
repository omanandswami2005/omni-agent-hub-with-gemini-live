import { create } from 'zustand';

export const useClientStore = create((set) => ({
  clients: [],
  setClients: (clients) => set({ clients }),
}));
