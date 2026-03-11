/**
 * useWebSocket — Raw WebSocket connection with exponential backoff reconnection.
 * Binary frames = audio, text frames = JSON control messages.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { createLiveConnection, sendBinaryAudio, sendJsonMessage, parseServerMessage, reconnectDelay } from '@/lib/ws';
import { auth } from '@/lib/firebase';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';

export function useWebSocket() {
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);
  const connectGenRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(async () => {
    // Bump generation so any older in-flight connect() bails after its await
    const gen = ++connectGenRef.current;

    // Close any existing connection synchronously (before the await gap)
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    intentionalClose.current = false;

    // Get a fresh Firebase token (async — may yield to other effects)
    const fbUser = auth.currentUser;
    if (!fbUser) return;
    let freshToken;
    try {
      freshToken = await fbUser.getIdToken();
    } catch {
      return;
    }

    // Bail if a newer connect() or disconnect() happened while we awaited
    if (connectGenRef.current !== gen || intentionalClose.current) return;

    const ws = createLiveConnection();
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      // Send auth handshake as first frame (token NOT in URL for security)
      // Include platform/OS info so the server can display it in the clients panel
      sendJsonMessage(ws, {
        type: 'auth',
        token: freshToken,
        user_agent: navigator.userAgent,
      });
    };

    ws.onmessage = (event) => {
      const msg = parseServerMessage(event);

      switch (msg.type) {
        case 'audio':
          useChatStore.getState().enqueueAudio(msg.data);
          break;
        case 'audio_blob':
          // Convert Blob to ArrayBuffer then enqueue
          msg.data.arrayBuffer().then((buf) => {
            useChatStore.getState().enqueueAudio(buf);
          });
          break;
        case 'transcription':
          useChatStore.getState().updateTranscript(msg);
          break;
        case 'response':
          useChatStore.getState().addMessage({
            role: 'assistant',
            content: msg.data,
            content_type: msg.content_type || 'text',
            genui_type: msg.genui?.type || msg.genui_type,
            genui_data: msg.genui?.data || msg.genui_data,
            persona: msg.persona,
          });
          break;
        case 'status':
          useChatStore.getState().setAgentState(msg.state);
          // On interruption, clear audio queue so stale playback stops
          if (msg.state === 'listening' && msg.detail === 'Interrupted by user') {
            useChatStore.getState().clearAudioQueue?.();
          }
          break;
        case 'tool_call':
          // Skip internal ADK multi-agent routing calls
          if (msg.tool_name === 'transfer_to_agent') break;
          useChatStore.getState().setToolActive(msg.tool_name, true);
          useChatStore.getState().addMessage({
            role: 'system',
            type: 'tool_call',
            content: `Using tool: ${msg.tool_name}`,
            tool_name: msg.tool_name,
            arguments: msg.arguments,
            status: msg.status,
          });
          break;
        case 'tool_response':
          // Skip internal ADK multi-agent routing responses
          if (msg.tool_name === 'transfer_to_agent') break;
          useChatStore.getState().setToolActive(msg.tool_name, false);
          useChatStore.getState().addMessage({
            role: 'system',
            type: 'tool_response',
            content: msg.result || `Tool ${msg.tool_name} completed`,
            tool_name: msg.tool_name,
            success: msg.success,
          });
          break;
        case 'image_response':
          useChatStore.getState().addMessage({
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
          }
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
      // 4000 = replaced by new connection, 4003 = auth failure — don't reconnect for either
      const noReconnect = e.code === 4000 || e.code === 4003;
      if (!intentionalClose.current && !noReconnect) {
        const delay = reconnectDelay(attemptRef.current);
        attemptRef.current += 1;
        reconnectTimer.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
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

  // Auto-connect when token is available
  useEffect(() => {
    const unsub = useAuthStore.subscribe((state) => {
      if (state.token && !wsRef.current) {
        connect();
      } else if (!state.token && wsRef.current) {
        disconnect();
      }
    });
    // Initial check
    if (useAuthStore.getState().token) connect();
    return () => {
      unsub();
      disconnect();
    };
  }, [connect, disconnect]);

  const sendText = useCallback((text) => {
    sendJsonMessage(wsRef.current, { type: 'text', content: text });
    useChatStore.getState().addMessage({
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });
  }, []);

  const sendAudio = useCallback((pcm16Buffer) => {
    sendBinaryAudio(wsRef.current, pcm16Buffer);
  }, []);

  const sendImage = useCallback((base64) => {
    sendJsonMessage(wsRef.current, { type: 'image', data_base64: base64 });
  }, []);

  const sendControl = useCallback((action, payload = {}) => {
    sendJsonMessage(wsRef.current, { type: 'control', action, ...payload });
  }, []);

  return { sendText, sendAudio, sendImage, sendControl, isConnected, disconnect };
}
