import { create } from 'zustand';
import { api } from '@/lib/api';

export const useMcpStore = create((set, get) => ({
  catalog: [],
  installed: [],
  loading: false,
  error: null,

  fetchCatalog: async () => {
    set({ loading: true, error: null });
    try {
      const catalog = await api.get('/plugins/catalog');
      set({ catalog, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  fetchEnabled: async () => {
    try {
      const installed = await api.get('/plugins/enabled');
      set({ installed });
    } catch { /* silent */ }
  },

  toggleMCP: async (mcpId, enabled) => {
    await api.post('/plugins/toggle', { plugin_id: mcpId, enabled });
    set((state) => ({
      catalog: state.catalog.map((m) => (m.id === mcpId ? { ...m, state: enabled ? 'enabled' : 'available' } : m)),
      installed: enabled
        ? [...state.installed, mcpId]
        : state.installed.filter((id) => id !== mcpId),
    }));
  },

  /** Start OAuth flow for an MCP_OAUTH plugin — opens popup. */
  startOAuth: async (pluginId) => {
    const data = await api.post(`/plugins/${pluginId}/oauth/start`);
    if (data?.auth_url) {
      const w = 600, h = 700;
      const left = window.screenX + (window.innerWidth - w) / 2;
      const top = window.screenY + (window.innerHeight - h) / 2;
      window.open(
        data.auth_url,
        'omni_oauth',
        `width=${w},height=${h},left=${left},top=${top},popup=1`,
      );
    }
    return data;
  },

  /** Disconnect an MCP_OAUTH plugin. */
  disconnectOAuth: async (pluginId) => {
    await api.post(`/plugins/${pluginId}/oauth/disconnect`);
    set((state) => ({
      catalog: state.catalog.map((m) =>
        m.id === pluginId ? { ...m, state: 'available' } : m,
      ),
      installed: state.installed.filter((id) => id !== pluginId),
    }));
  },

  /** Save user-provided secrets (API keys) for a plugin. */
  saveSecrets: async (pluginId, secrets) => {
    await api.post('/plugins/secrets', { plugin_id: pluginId, secrets });
  },

  /** Start Google OAuth flow for a native plugin — opens popup. */
  startGoogleOAuth: async (pluginId) => {
    const data = await api.post(`/plugins/${pluginId}/google-oauth/start`);
    if (data?.auth_url) {
      const w = 600, h = 700;
      const left = window.screenX + (window.innerWidth - w) / 2;
      const top = window.screenY + (window.innerHeight - h) / 2;
      window.open(
        data.auth_url,
        'omni_google_oauth',
        `width=${w},height=${h},left=${left},top=${top},popup=1`,
      );
    }
    return data;
  },

  /** Disconnect a Google OAuth native plugin. */
  disconnectGoogleOAuth: async (pluginId) => {
    await api.post(`/plugins/${pluginId}/google-oauth/disconnect`);
    set((state) => ({
      catalog: state.catalog.map((m) =>
        m.id === pluginId ? { ...m, state: 'available' } : m,
      ),
      installed: state.installed.filter((id) => id !== pluginId),
    }));
  },

  /** Called when OAuth popup sends a postMessage back. */
  handleOAuthCallback: (pluginId, status) => {
    if (status === 'success') {
      set((state) => ({
        catalog: state.catalog.map((m) =>
          m.id === pluginId ? { ...m, state: 'connected' } : m,
        ),
        installed: state.installed.includes(pluginId)
          ? state.installed
          : [...state.installed, pluginId],
      }));
    }
  },

  /**
   * After OAuth success, re-fetch the catalog with retries until the
   * connected plugin reports tools. This handles the case where the OAuth
   * callback hit a different Cloud Run instance than the catalog request
   * (in-memory _discovered_summaries lives per-instance).
   */
  refreshAfterOAuth: async (pluginId) => {
    const delays = [800, 2000, 3500, 5000];
    for (let i = 0; i < delays.length; i++) {
      await new Promise((r) => setTimeout(r, delays[i]));
      await get().fetchCatalog();

      // Preserve connected state even if server briefly reports enabled
      const item = get().catalog.find((m) => m.id === pluginId);
      if (item && item.state !== 'connected') {
        set((state) => ({
          catalog: state.catalog.map((m) =>
            m.id === pluginId ? { ...m, state: 'connected' } : m,
          ),
        }));
      }

      if (item?.tools_summary?.length > 0 || item?.tools?.length > 0) return;
    }
  },

  setCatalog: (catalog) => set({ catalog }),
  setInstalled: (installed) => set({ installed }),
  setLoading: (loading) => set({ loading }),
}));
