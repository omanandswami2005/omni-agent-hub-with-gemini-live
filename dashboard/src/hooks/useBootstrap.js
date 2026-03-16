/**
 * useBootstrap — Fetches all initial data in a single API call on app mount.
 *
 * Replaces sequential fetches of sessions, personas, and MCP catalog
 * with one GET /init round-trip. Called once from AppShell when authenticated.
 */

import { useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { usePersonaStore } from '@/stores/personaStore';
import { useMcpStore } from '@/stores/mcpStore';

export function useBootstrap() {
    const fetched = useRef(false);
    const token = useAuthStore((s) => s.token);

    useEffect(() => {
        if (!token || fetched.current) return;
        fetched.current = true;

        api.get('/init').then((data) => {
            if (data.sessions) useSessionStore.getState().setSessions(data.sessions);
            if (data.personas) {
                usePersonaStore.getState().setPersonas(data.personas);
                // Auto-select first persona if none active
                if (!usePersonaStore.getState().activePersona && data.personas.length > 0) {
                    usePersonaStore.getState().setActivePersona(data.personas[0]);
                }
            }
            // Prefer plugin_catalog (full PluginStatus with tools_summary, state,
            // kind, etc.) over mcp_catalog (stripped MCPCatalogItem).
            const catalog = data.plugin_catalog || data.mcp_catalog;
            if (catalog) useMcpStore.getState().setCatalog(catalog);
            if (data.mcp_enabled) useMcpStore.getState().setInstalled(data.mcp_enabled);
        }).catch(() => {
            // Silent — individual pages can still fetch their own data as fallback
        });
    }, [token]);
}
