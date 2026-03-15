/**
 * useWebSocket — Raw WebSocket connection with exponential backoff reconnection.
 * Binary frames = audio, text frames = JSON control messages.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { toast } from 'sonner';
import { createLiveConnection, sendBinaryAudio, sendJsonMessage, parseServerMessage, reconnectDelay } from '@/lib/ws';
import { auth } from '@/lib/firebase';
import { getClientType } from '@/lib/constants';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useSessionSuggestionStore } from '@/stores/sessionSuggestionStore';
import { usePersonaStore } from '@/stores/personaStore';

export function useWebSocket() {
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const reconnectTimer = useRef(null);
  const intentionalClose = useRef(false);
  const connectGenRef = useRef(0);
  // True once the server has granted the mic floor to this client.
  // sendAudio drops frames until this is true, preventing audio from reaching
  // ADK before the explicit mic_acquire handshake completes.
  const micGrantedRef = useRef(false);
  // Callback invoked once when mic floor is granted (used by VoiceProvider
  // to defer startRecording until the server is ready to accept audio).
  const onMicGrantedRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  // Firestore session ID returned by the server after auth
  const [serverSessionId, setServerSessionId] = useState(null);

  const connect = useCallback(async () => {
    // Bump generation so any older in-flight connect() bails after its await
    const gen = ++connectGenRef.current;

    // Close any existing connection synchronously (before the await gap).
    // Null out onclose FIRST so the backoff-reconnect handler never fires for
    // this intentional tear-down (the callback is always async — clearing the
    // ref alone is not enough to prevent it from firing).
    if (wsRef.current) {
      wsRef.current.onclose = null;
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
      micGrantedRef.current = false; // reset on every (re)connect — must re-acquire
      // Send auth handshake as first frame (token NOT in URL for security)
      // Include platform/OS info so the server can display it in the clients panel
      const activeId = useSessionStore.getState().activeSessionId;
      const wantsNew = useSessionStore.getState().wantsNewSession;
      const activePersona = usePersonaStore.getState().activePersona;

      // Determine session_id to send
      let sessionIdToSend = undefined;
      if (wantsNew) {
        sessionIdToSend = "new";
        // Clear the flag after sending
        useSessionStore.getState().setWantsNewSession(false);
      } else if (activeId) {
        sessionIdToSend = activeId;
      }

      sendJsonMessage(ws, {
        type: 'auth',
        token: freshToken,
        client_type: getClientType(),
        user_agent: navigator.userAgent,
        ...(sessionIdToSend !== undefined ? { session_id: sessionIdToSend } : {}),
        ...(activePersona?.id ? { persona_id: activePersona.id } : {}),
        ...(activePersona?.voice ? { voice: activePersona.voice } : {}),
      });
    };

    ws.onmessage = (event) => {
      const msg = parseServerMessage(event);
      const fromOtherDevice = msg.cross_client === true;

      // Cross-client events (from other devices) are rendered exclusively by
      // useChatWebSocket (/ws/chat), which has its own EventBus relay.
      // Handling them here too would cause every message to appear twice.
      // Only keep handling for audio, status, and auth which are live-specific.
      if (fromOtherDevice) {
        switch (msg.type) {
          case 'status':
            // Let the other device's status not affect our own agent state
            break;
          case 'client_status_update':
            useClientStore.getState().setClients(msg.clients);
            break;
          case 'session_suggestion': {
            // Another device started a session — switch to it for continuity
            if (msg.session_id) {
              const ss = useSessionStore.getState();
              // Guard: don't reconnect if already on this session
              if (ss.activeSessionId === msg.session_id) break;
              ss.setActiveSession(msg.session_id);
              ss.ensureSession(msg.session_id);
              setServerSessionId(msg.session_id);
              const sss = useSessionSuggestionStore.getState();
              if (sss.autoJoin) {
                toast.info(`Joined session from ${msg.available_clients?.join(', ') || 'another device'}`, { duration: 3000 });
              } else {
                sss.setSuggestion({
                  availableClients: msg.available_clients || [],
                  message: msg.message || 'Active session on another device.',
                  sessionId: msg.session_id,
                });
              }
              // Reconnect the live WS to the new session
              setTimeout(() => {
                if (wsRef.current) {
                  wsRef.current.onclose = null;
                  wsRef.current.close();
                  wsRef.current = null;
                }
                connect();
              }, 150);
            }
            break;
          }
          default:
            break;
        }
        return;
      }

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
          // On interruption, clear audio queue and cancel any active tools
          if (msg.detail && msg.detail.toLowerCase().includes('interrupt')) {
            useChatStore.getState().clearAudioQueue?.();
            useChatStore.getState().cancelAllActions?.();
          }
          break;
        case 'tool_call':
          // Agent transfers get their own collapsible card
          if (msg.tool_name === 'transfer_to_agent') break;
          useChatStore.getState().setToolActive(msg.tool_name, true);
          useChatStore.getState().addAction({
            tool_name: msg.tool_name,
            arguments: msg.arguments,
            status: msg.status,
            action_kind: msg.action_kind || 'tool',
            source_label: msg.source_label || '',
            call_id: msg.call_id || '',
          });
          break;
        case 'tool_response':
          // Skip internal ADK multi-agent routing responses
          if (msg.tool_name === 'transfer_to_agent') break;
          useChatStore.getState().setToolActive(msg.tool_name, false);
          useChatStore.getState().completeAction(msg.tool_name, {
            result: msg.result || `Tool ${msg.tool_name} completed`,
            success: msg.success,
            action_kind: msg.action_kind || 'tool',
            source_label: msg.source_label || '',
          }, msg.call_id || '');
          break;
        case 'agent_transfer':
          useChatStore.getState().addAction({
            type: 'agent_transfer',
            tool_name: 'transfer_to_agent',
            to_agent: msg.to_agent || '',
            from_agent: msg.from_agent || '',
            message: msg.message || '',
            action_kind: 'agent_transfer',
            responded: true,
            success: true,
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
            if (msg.firestore_session_id) {
              setServerSessionId(msg.firestore_session_id);
              const ss = useSessionStore.getState();
              ss.setActiveSession(msg.firestore_session_id);
              ss.ensureSession(msg.firestore_session_id);
            }
          }
          break;
        case 'session_created': {
          // Server lazily created a Firestore session on first message
          if (msg.firestore_session_id) {
            setServerSessionId(msg.firestore_session_id);
            const ss = useSessionStore.getState();
            ss.setActiveSession(msg.firestore_session_id);
            ss.ensureSession(msg.firestore_session_id);
          }
          break;
        }
        case 'client_status_update':
          useClientStore.getState().setClients(msg.clients);
          break;
        case 'mic_floor':
          if (msg.event === 'granted') {
            // Server granted us the mic floor — start forwarding audio frames
            micGrantedRef.current = true;
            useClientStore.getState().setMicFloorHolder(msg.holder || null);
            // Fire the pending callback (e.g. startRecording) now that server is ready
            if (onMicGrantedRef.current) {
              onMicGrantedRef.current();
              onMicGrantedRef.current = null;
            }
          } else if (msg.event === 'denied') {
            // Server denied our acquire request — another device holds the floor
            micGrantedRef.current = false;
            onMicGrantedRef.current = null;
            useClientStore.getState().setMicFloorHolder(msg.holder || null);
          } else if (msg.event === 'acquired' || msg.event === 'released') {
            useClientStore.getState().setMicFloorHolder(
              msg.event === 'acquired' ? (msg.holder || null) : null
            );
          } else if (msg.event === 'busy') {
            // Fallback path: server rejected a raw audio frame (no mic_acquire sent).
            micGrantedRef.current = false;
            useClientStore.getState().setMicFloorHolder(msg.holder || null);
          }
          break;
        case 'session_suggestion': {
          const sss = useSessionSuggestionStore.getState();
          const myType = getClientType();
          // Ignore suggestions that are only about our own client type — these
          // are self-broadcasts from our own connection, not a different device.
          const isSelfBroadcast =
            (msg.available_clients || []).length === 1 &&
            msg.available_clients[0] === myType;
          // If the server included a session_id, switch to it for continuity
          if (msg.session_id && !isSelfBroadcast) {
            const ss = useSessionStore.getState();
            if (ss.activeSessionId !== msg.session_id) {
              ss.setActiveSession(msg.session_id);
              ss.ensureSession(msg.session_id);
              setServerSessionId(msg.session_id);
              // Delay reconnect slightly so store has time to update
              setTimeout(() => {
                if (wsRef.current) {
                  wsRef.current.onclose = null;
                  wsRef.current.close();
                  wsRef.current = null;
                }
                connect();
              }, 100);
            }
          }
          if (!isSelfBroadcast) {
            if (sss.autoJoin) {
              toast.info(`Joined your active session from ${msg.available_clients?.join(', ') || 'another device'}`, { duration: 3000 });
            } else {
              sss.setSuggestion({
                availableClients: msg.available_clients || [],
                message: msg.message || 'You have an active session on another device.',
                sessionId: msg.session_id || '',
              });
            }
          }
          break;
        }
        case 'error': {
          const description = msg.description || 'An unexpected error occurred.';
          toast.error(description, { duration: 6000 });
          useChatStore.getState().addMessage({
            role: 'system',
            type: 'error',
            content: description,
            error_code: msg.code,
          });
          useChatStore.getState().setAgentState('idle');
          break;
        }
        default:
          break;
      }
    };

    ws.onclose = (e) => {
      setIsConnected(false);
      // 4000 = replaced by new connection, 4003 = auth failure — don't reconnect for either
      const noReconnect = e.code === 4000 || e.code === 4003;
      if (e.code === 4003) {
        toast.error('Authentication failed. Please sign in again.', { duration: 6000 });
      }
      clearTimeout(reconnectTimer.current);
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

  // Reconnect (close + re-open) — used when switching sessions
  const reconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    connect();
  }, [connect]);

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
    // Add user message to chat immediately (optimistic)
    useChatStore.getState().addMessage({
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      sendJsonMessage(wsRef.current, { type: 'text', content: text });
    } else {
      useChatStore.getState().addMessage({
        id: `err-${Date.now()}`,
        role: 'system',
        content: 'Message could not be sent — reconnecting…',
        timestamp: new Date().toISOString(),
      });
    }
  }, []);

  const sendAudio = useCallback((pcm16Buffer) => {
    // Only forward audio frames after the server has granted the mic floor.
    // This prevents frames from reaching ADK before the mic_acquire handshake
    // completes (or when another device holds the floor).
    if (!micGrantedRef.current) return;
    sendBinaryAudio(wsRef.current, pcm16Buffer);
  }, []);

  const sendImage = useCallback((base64) => {
    sendJsonMessage(wsRef.current, { type: 'image', data_base64: base64 });
  }, []);

  const sendControl = useCallback((action, payload = {}) => {
    sendJsonMessage(wsRef.current, { type: 'control', action, ...payload });
  }, []);

  // Send explicit mic floor acquire request before streaming audio.
  // The server will respond with mic_floor:{event:"granted"} or {event:"denied"}.
  // Optional *onGranted* callback is invoked once when the floor is granted.
  const acquireMic = useCallback((onGranted) => {
    micGrantedRef.current = false; // wait for server grant
    onMicGrantedRef.current = onGranted || null;
    sendJsonMessage(wsRef.current, { type: 'mic_acquire' });
  }, []);

  // Send explicit mic floor release when recording stops.
  const releaseMic = useCallback(() => {
    micGrantedRef.current = false;
    sendJsonMessage(wsRef.current, { type: 'mic_release' });
  }, []);

  return { sendText, sendAudio, sendImage, sendControl, acquireMic, releaseMic, isConnected, disconnect, reconnect, serverSessionId };
}
