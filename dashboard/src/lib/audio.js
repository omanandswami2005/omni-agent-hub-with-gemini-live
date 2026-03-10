/**
 * Audio utilities for PCM capture and playback.
 */

export const CAPTURE_SAMPLE_RATE = 16000;
export const PLAYBACK_SAMPLE_RATE = 24000;

/**
 * Convert Float32 audio [-1, 1] to Int16 PCM.
 */
export function float32ToPcm16(float32Array) {
  const pcm16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16.buffer;
}

/**
 * Convert Int16 PCM to Float32 [-1, 1] for playback.
 */
export function pcm16ToFloat32(pcm16Buffer) {
  const pcm16 = new Int16Array(pcm16Buffer);
  const float32 = new Float32Array(pcm16.length);
  for (let i = 0; i < pcm16.length; i++) {
    float32[i] = pcm16[i] / (pcm16[i] < 0 ? 0x8000 : 0x7fff);
  }
  return float32;
}

/**
 * Compute RMS volume level from PCM Int16 data.
 * Returns a value between 0 and 1.
 */
export function calculateVolume(pcm16Buffer) {
  const samples = new Int16Array(pcm16Buffer);
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const normalized = samples[i] / 0x7fff;
    sum += normalized * normalized;
  }
  return Math.sqrt(sum / samples.length);
}

/**
 * Linear resample from one sample rate to another.
 */
export function resample(float32Array, fromRate, toRate) {
  if (fromRate === toRate) return float32Array;
  const ratio = fromRate / toRate;
  const newLength = Math.round(float32Array.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const srcIndex = i * ratio;
    const low = Math.floor(srcIndex);
    const high = Math.min(low + 1, float32Array.length - 1);
    const frac = srcIndex - low;
    result[i] = float32Array[low] * (1 - frac) + float32Array[high] * frac;
  }
  return result;
}

/**
 * AudioWorklet processor code as a Blob URL.
 * Captures mono Float32 samples and posts them to the main thread.
 */
export function createCaptureWorkletUrl() {
  const code = `
    class CaptureProcessor extends AudioWorkletProcessor {
      process(inputs) {
        const input = inputs[0];
        if (input && input[0] && input[0].length > 0) {
          this.port.postMessage(new Float32Array(input[0]));
        }
        return true;
      }
    }
    registerProcessor('capture-processor', CaptureProcessor);
  `;
  const blob = new Blob([code], { type: 'application/javascript' });
  return URL.createObjectURL(blob);
}
