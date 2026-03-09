import { create } from 'zustand';

export const useMcpStore = create((set) => ({
  catalog: [],
  installed: [],
  loading: false,

  setCatalog: (catalog) => set({ catalog }),
  setInstalled: (installed) => set({ installed }),
  setLoading: (loading) => set({ loading }),
}));
