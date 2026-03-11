/**
 * useChatWebSocket — Dedicated WebSocket connection to /ws/chat for
 * reliable ADK-powered text chat (independent of the audio live session).
 *
 * Supports tool calls, transcription display, and GenUI — same message
 * protocol as /ws/live but uses ADK runner.run_async() instead of run_live().
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { auth } from '@/lib/firebase';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';
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
            ws.send(
                JSON.stringify({
                    type: 'auth',
                    token,
                    user_agent: navigator.userAgent,
                }),
            );
        };

        ws.onmessage = (event) => {
            const msg = parseServerMessage(event);
            const store = useChatStore.getState();

            switch (msg.type) {
                case 'response':
                    store.addMessage({
                        role: 'assistant',
                        content: msg.data,
                        content_type: msg.content_type || 'text',
                        genui_type: msg.genui?.type || msg.genui_type,
                        genui_data: msg.genui?.data || msg.genui_data,
                        persona: msg.persona,
                    });
                    break;
                case 'transcription':
                    store.updateTranscript?.(msg);
                    break;
                case 'status':
                    store.setAgentState(msg.state);
                    break;
                case 'tool_call':
                    if (msg.tool_name === 'transfer_to_agent') break;
                    store.setToolActive(msg.tool_name, true);
                    store.addMessage({
                        role: 'system',
                        type: 'tool_call',
                        content: `Using tool: ${msg.tool_name}`,
                        tool_name: msg.tool_name,
                        arguments: msg.arguments,
                        status: msg.status,
                    });
                    break;
                case 'tool_response':
                    if (msg.tool_name === 'transfer_to_agent') break;
                    store.setToolActive(msg.tool_name, false);
                    store.addMessage({
                        role: 'system',
                        type: 'tool_response',
                        content: msg.result || `Tool ${msg.tool_name} completed`,
                        tool_name: msg.tool_name,
                        success: msg.success,
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
                    if (msg.status === 'ok') setIsConnected(true);
                    break;
                case 'client_status_update':
                    useClientStore.getState().setClients(msg.clients);
                    break;
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
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'text', content: text }));
        }
        // Add user message to chat immediately
        useChatStore.getState().addMessage({
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date().toISOString(),
        });
    }, []);

    return { sendText, isConnected };
}
