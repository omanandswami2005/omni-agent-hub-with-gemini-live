/**
 * useAudioCapture — Mic → AudioWorklet → PCM16 16kHz → WebSocket binary frames.
 */

// TODO: Implement audio capture hook:
//   - getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } })
//   - AudioContext → AudioWorkletNode → PCM16 Int16Array
//   - Send as binary WS frame (not base64)

export function useAudioCapture() {
  return { startRecording: () => {}, stopRecording: () => {}, isRecording: false };
}
