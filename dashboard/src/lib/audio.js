/**
 * Audio utilities for PCM capture and playback.
 */

// TODO: Implement:
//   - AudioWorklet processor registration
//   - PCM16 float32-to-int16 conversion
//   - Resampling (browser native rate → 16kHz for capture)
//   - AudioContext management (24kHz for playback)
//   - Audio queue/buffer management

export const CAPTURE_SAMPLE_RATE = 16000;
export const PLAYBACK_SAMPLE_RATE = 24000;

export function float32ToPcm16(float32Array) {
  const pcm16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16.buffer;
}

export function pcm16ToFloat32(pcm16Buffer) {
  const pcm16 = new Int16Array(pcm16Buffer);
  const float32 = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i++) {
    float32[i] = pcm16[i] / (pcm16[i] < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}
