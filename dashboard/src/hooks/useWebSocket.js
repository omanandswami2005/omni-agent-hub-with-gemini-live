/**
 * useWebSocket — Raw WebSocket connection with exponential backoff reconnection.
 * Binary frames = audio, text frames = JSON control messages.
 */

// TODO: Implement raw WebSocket hook:
//   - connect(sessionId, token)
//   - sendText(text), sendAudio(pcmData), sendImage(base64), sendControl(action)
//   - Exponential backoff: [1s, 2s, 4s, 8s, 16s]
//   - Auth via first JSON message { type: "auth", token }
//   - Binary onmessage → chatStore.enqueueAudio
//   - Text onmessage → JSON.parse → dispatch by msg.type

export function useWebSocket() {
  // Stub — implementation pending
  return { sendText: () => {}, sendAudio: () => {}, sendImage: () => {}, sendControl: () => {} };
}
