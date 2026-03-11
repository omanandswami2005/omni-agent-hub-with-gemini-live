/**
 * useWebSocket — Raw WebSocket connection with exponential backoff reconnection.
 * Binary frames = audio, text frames = JSON control messages.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { createLiveConnection, sendBinaryAudio, sendJsonMessage, parseServerMessage, reconnectDelay } from '@/lib/ws';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';

export function useWebSocket() {
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef(null);
  const [isConnected, setIsConnected] = useState(false);

  const connect = useCallback(() => {
    const token = useAuthStore.getState().token;
    if (!token) return;

    // Cleanup previous
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = createLiveConnection(token);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      attemptRef.current = 0;
      setIsConnected(true);
      // Send auth handshake
      sendJsonMessage(ws, { type: 'auth', token });
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
        case 'transcript':
          useChatStore.getState().updateTranscript(msg);
          break;
        case 'response':
          useChatStore.getState().addMessage({
            id: msg.id || Date.now().toString(),
            role: 'assistant',
            content: msg.data,
            persona: msg.persona,
            timestamp: msg.timestamp || new Date().toISOString(),
            genui: msg.genuI,
          });
          break;
        case 'status':
          useChatStore.getState().setAgentState(msg.state);
          break;
        case 'tool_call':
          useChatStore.getState().setToolActive(msg.tool_name, true);
          break;
        case 'tool_response':
          useChatStore.getState().setToolActive(msg.tool_name, false);
          break;
        case 'auth_response':
          // Auth accepted — nothing extra needed
          break;
        default:
          break;
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      // Reconnect with backoff
      const delay = reconnectDelay(attemptRef.current);
      attemptRef.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimer.current);
    attemptRef.current = 0;
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
