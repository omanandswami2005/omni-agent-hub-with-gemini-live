/**
 * useAudioPlayback — WebSocket binary → PCM16 24kHz → AudioBufferQueue → speakers.
 */

// TODO: Implement audio playback hook:
//   - AudioContext(sampleRate: 24000)
//   - Ring buffer (180s of audio)
//   - Int16 → Float32 conversion
//   - Stall detection + recovery

export function useAudioPlayback() {
  return { isPlaying: false };
}
