/**
 * useChatWebSocket — Dedicated WebSocket connection to /ws/chat for
 * reliable ADK-powered text chat (independent of the audio live session).
 *
 * Supports tool calls, transcription display, and GenUI — same message
 * protocol as /ws/live but uses ADK runner.run_async() instead of run_live().
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from 'sonner';
import { auth } from '@/lib/firebase';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';
import { useSessionStore } from '@/stores/sessionStore';
import { parseServerMessage, reconnectDelay } from '@/lib/ws';

const CHAT_WS_URL =
    import.meta.env.VITE_CHAT_WS_URL ||
    `${import.meta.env.VITE_WS_URL?.replace('/live', '/chat') ?? `ws://${window.location.host}/ws/chat`}`;

export function useChatWebSocket() {
    const wsRef = useRef(null);
    const attemptRef = useRef(0);
    const reconnectTimer = useRef(null);
    const intentionalClose = useRef(false);
    const connectGenRef = useRef(0);
    const [isConnected, setIsConnected] = useState(false);
    // Firestore session ID returned by the server after auth
    const [serverSessionId, setServerSessionId] = useState(null);

    const connect = useCallback(async () => {
        const gen = ++connectGenRef.current;
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        intentionalClose.current = false;

        const fbUser = auth.currentUser;
        if (!fbUser) return;
        let token;
        try {
            token = await fbUser.getIdToken();
        } catch {
            return;
        }
        if (connectGenRef.current !== gen || intentionalClose.current) return;

        const ws = new WebSocket(CHAT_WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
            attemptRef.current = 0;
            // Send session_id if we have one so the server resumes that session
            const activeId = useSessionStore.getState().activeSessionId;
            ws.send(
                JSON.stringify({
                    type: 'auth',
                    token,
                    user_agent: navigator.userAgent,
                    ...(activeId ? { session_id: activeId } : {}),
                }),
            );
        };

        ws.onmessage = (event) => {
            const msg = parseServerMessage(event);
            const store = useChatStore.getState();

            // cross_client:true means this event originated from another device
            // (e.g. a mobile /ws/live session). Tag the message so the UI can
            // display a visual indicator.
            const fromOtherDevice = msg.cross_client === true;

            switch (msg.type) {
                case 'response':
                    store.addMessage({
                        role: 'assistant',
                        content: msg.data,
                        content_type: msg.content_type || 'text',
                        genui_type: msg.genui?.type || msg.genui_type,
                        genui_data: msg.genui?.data || msg.genui_data,
                        persona: msg.persona,
                        ...(fromOtherDevice && { cross_client: true }),
                    });
                    break;
                case 'transcription':
                    // Forward voice transcriptions from other devices into chat
                    if (fromOtherDevice && msg.text) {
                        store.addMessage({
                            role: msg.direction === 'input' ? 'user' : 'assistant',
                            content: msg.text,
                            content_type: 'text',
                            cross_client: true,
                            is_transcription: true,
                        });
                    } else {
                        store.updateTranscript?.(msg);
                    }
                    break;
                case 'status':
                    // Only propagate status from this device's own session
                    if (!fromOtherDevice) store.setAgentState(msg.state);
                    break;
                case 'tool_call':
                    if (msg.tool_name === 'transfer_to_agent') break;
                    store.setToolActive(msg.tool_name, true);
                    store.addAction({
                        tool_name: msg.tool_name,
                        arguments: msg.arguments,
                        status: msg.status,
                        action_kind: msg.action_kind || 'tool',
                        source_label: msg.source_label || '',
                        ...(fromOtherDevice && { cross_client: true }),
                    });
                    break;
                case 'tool_response':
                    if (msg.tool_name === 'transfer_to_agent') break;
                    store.setToolActive(msg.tool_name, false);
                    store.completeAction(msg.tool_name, {
                        result: msg.result || `Tool ${msg.tool_name} completed`,
                        success: msg.success,
                        action_kind: msg.action_kind || 'tool',
                        source_label: msg.source_label || '',
                    });
                    break;
                case 'image_response':
                    store.addMessage({
                        role: 'assistant',
                        type: 'image',
                        tool_name: msg.tool_name,
                        image_base64: msg.image_base64,
                        mime_type: msg.mime_type,
                        image_url: msg.image_url,
                        description: msg.description,
                        images: msg.images,
                        text: msg.text,
                        parts: msg.parts,
                        timestamp: new Date().toISOString(),
                    });
                    break;
                case 'auth_response':
                    if (msg.status === 'ok') {
                        setIsConnected(true);
                        // Capture the Firestore session ID for URL routing
                        if (msg.firestore_session_id) {
                            setServerSessionId(msg.firestore_session_id);
                            const ss = useSessionStore.getState();
                            ss.setActiveSession(msg.firestore_session_id);
                            ss.ensureSession(msg.firestore_session_id);
                        }
                    }
                    break;
                case 'client_status_update':
                    useClientStore.getState().setClients(msg.clients);
                    break;
                case 'session_suggestion': {
                    // If the server included a session_id, switch to it
                    if (msg.session_id) {
                        const ss = useSessionStore.getState();
                        ss.setActiveSession(msg.session_id);
                        ss.ensureSession(msg.session_id);
                    }
                    break;
                }
                case 'error': {
                    const description = msg.description || 'An unexpected error occurred.';
                    toast.error(description, { duration: 6000 });
                    store.addMessage({
                        role: 'system',
                        type: 'error',
                        content: description,
                        error_code: msg.code,
                    });
                    store.setAgentState('idle');
                    break;
                }
                default:
                    break;
            }
        };

        ws.onclose = (e) => {
            setIsConnected(false);
            const noReconnect = e.code === 4000 || e.code === 4003;
            if (!intentionalClose.current && !noReconnect) {
                const delay = reconnectDelay(attemptRef.current);
                attemptRef.current += 1;
                reconnectTimer.current = setTimeout(connect, delay);
            }
        };

        ws.onerror = () => ws.close();
    }, []);

    const disconnect = useCallback(() => {
        clearTimeout(reconnectTimer.current);
        attemptRef.current = 0;
        intentionalClose.current = true;
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setIsConnected(false);
    }, []);

    // Reconnect when session changes (user navigated to a different session)
    const reconnect = useCallback(() => {
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        connect();
    }, [connect]);

    useEffect(() => {
        const unsub = useAuthStore.subscribe((state) => {
            if (state.token && !wsRef.current) connect();
            else if (!state.token && wsRef.current) disconnect();
        });
        if (useAuthStore.getState().token) connect();
        return () => {
            unsub();
            disconnect();
        };
    }, [connect, disconnect]);

    const sendText = useCallback((text) => {
        // Add user message to chat immediately (optimistic)
        useChatStore.getState().addMessage({
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date().toISOString(),
        });

        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'text', content: text }));
        } else {
            // WS not connected — inform the user instead of silently dropping
            useChatStore.getState().addMessage({
                id: `err-${Date.now()}`,
                role: 'system',
                content: 'Message could not be sent — reconnecting…',
                timestamp: new Date().toISOString(),
            });
        }
    }, []);

    return { sendText, isConnected, serverSessionId, reconnect };
}
