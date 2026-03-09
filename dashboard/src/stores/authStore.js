import { create } from 'zustand';

export const useAuthStore = create((set) => ({
  user: null,
  token: null,
  loading: true,

  setUser: (user, token) => set({ user, token, loading: false }),
  logout: () => set({ user: null, token: null, loading: false }),
  setLoading: (loading) => set({ loading }),
}));
