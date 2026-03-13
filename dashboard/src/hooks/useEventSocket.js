/**
 * useEventSocket — Connects to /ws/events for dashboard push notifications.
 *
 * This is a separate WebSocket from the main /ws/live audio channel.
 * It receives JSON events: pipeline_created, pipeline_progress, etc.
 * Events are routed to the pipelineStore (and optionally agentActivityStore).
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { auth } from '@/lib/firebase';
import { useAuthStore } from '@/stores/authStore';
import { usePipelineStore } from '@/stores/pipelineStore';

/**
 * Derive the /ws/events URL from VITE_WS_URL or current host,
 * reusing the same base as the live connection.
 */
function getEventsUrl() {
    const base = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws/live`;
    // Replace /ws/live → /ws/events
    return base.replace(/\/ws\/live\/?$/, '/ws/events');
}

export function useEventSocket() {
    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);
    const intentionalClose = useRef(false);
    const [isConnected, setIsConnected] = useState(false);

    const isLoggedIn = useAuthStore((s) => !!s.user);

    const connect = useCallback(async () => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        const token = await auth.currentUser?.getIdToken();
        if (!token) return;

        const url = getEventsUrl();
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            // Send auth message (same pattern as ws_live)
            ws.send(JSON.stringify({ type: 'auth', token }));
        };

        ws.onmessage = (event) => {
            if (typeof event.data !== 'string') return;
            try {
                const msg = JSON.parse(event.data);

                // Auth response
                if (msg.status === 'ok' && msg.user_id) {
                    setIsConnected(true);
                    return;
                }
                if (msg.status === 'error') {
                    return;
                }

                // Route pipeline events
                usePipelineStore.getState().handleEvent(msg);
            } catch {
                // ignore non-JSON
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
            wsRef.current = null;
            if (!intentionalClose.current) {
                reconnectTimer.current = setTimeout(connect, 5000);
            }
        };

        ws.onerror = () => {
            // onclose will fire after this
        };
    }, []);

    const disconnect = useCallback(() => {
        intentionalClose.current = true;
        clearTimeout(reconnectTimer.current);
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
    }, []);

    // Auto-connect when logged in, disconnect when logged out
    useEffect(() => {
        if (isLoggedIn) {
            intentionalClose.current = false;
            connect();
        } else {
            disconnect();
        }
        return () => disconnect();
    }, [isLoggedIn, connect, disconnect]);

    return { isConnected };
}
