/**
 * Raw WebSocket helpers for Gemini Live connection.
 */

// TODO: Implement WS protocol helpers:
//   - createLiveConnection(token) → WebSocket
//   - sendAudioChunk(ws, pcm16ArrayBuffer) → binary frame
//   - sendTextMessage(ws, text) → JSON text frame
//   - sendControlMessage(ws, action) → JSON text frame
//   - parseServerMessage(event) → typed message object
//   - WS URL from VITE_WS_URL env var

export const WS_URL = import.meta.env.VITE_WS_URL || `ws://${window.location.host}/ws/live`;

export function createLiveConnection(token) {
  const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
  return new WebSocket(url);
}

export function sendBinaryAudio(ws, pcm16Buffer) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(pcm16Buffer);
  }
}

export function sendJsonMessage(ws, message) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}
