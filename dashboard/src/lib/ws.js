/**
 * Raw WebSocket helpers for Gemini Live connection.
 */

import { WS_RECONNECT_MIN_MS, WS_RECONNECT_MAX_MS } from '@/lib/constants';

export const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws/live`;

export function createLiveConnection() {
  return new WebSocket(WS_URL);
}

export function sendBinaryAudio(ws, pcm16Buffer) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(pcm16Buffer);
  }
}

export function sendJsonMessage(ws, message) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

/**
 * Parse an incoming server message.
 * Binary frames → { type: 'audio', data: ArrayBuffer }
 * Text frames → parsed JSON
 */
export function parseServerMessage(event) {
  if (event.data instanceof ArrayBuffer) {
    return { type: 'audio', data: event.data };
  }
  if (event.data instanceof Blob) {
    return { type: 'audio_blob', data: event.data };
  }
  try {
    return JSON.parse(event.data);
  } catch {
    return { type: 'unknown', raw: event.data };
  }
}

/**
 * Calculate reconnect delay with exponential backoff + jitter.
 */
export function reconnectDelay(attempt) {
  const base = Math.min(WS_RECONNECT_MIN_MS * 2 ** attempt, WS_RECONNECT_MAX_MS);
  return base + Math.random() * 1000;
}
