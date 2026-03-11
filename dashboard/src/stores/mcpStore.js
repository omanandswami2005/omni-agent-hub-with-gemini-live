import { create } from 'zustand';
import { api } from '@/lib/api';

export const useMcpStore = create((set, _get) => ({
  catalog: [],
  installed: [],
  loading: false,
  error: null,

  fetchCatalog: async () => {
    set({ loading: true, error: null });
    try {
      const catalog = await api.get('/mcp/catalog');
      set({ catalog, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  fetchEnabled: async () => {
    try {
      const installed = await api.get('/mcp/enabled');
      set({ installed });
    } catch { /* silent */ }
  },

  toggleMCP: async (mcpId, enabled) => {
    await api.post('/mcp/toggle', { mcp_id: mcpId, enabled });
    set((state) => ({
      catalog: state.catalog.map((m) => (m.id === mcpId ? { ...m, enabled } : m)),
      installed: enabled
        ? [...state.installed, mcpId]
        : state.installed.filter((id) => id !== mcpId),
    }));
  },

  setCatalog: (catalog) => set({ catalog }),
  setInstalled: (installed) => set({ installed }),
  setLoading: (loading) => set({ loading }),
}));
