/**
 * useAudioCapture — Mic → AudioWorklet → PCM16 16kHz → callback.
 *
 * Permission errors (DOMException names):
 *  - NotAllowedError  → user clicked "Block" / "Never allow"
 *  - NotFoundError    → no microphone detected
 *  - NotReadableError → device busy (another app has the mic)
 *  - SecurityError    → insecure context
 */

import { useRef, useState, useCallback } from 'react';
import { CAPTURE_SAMPLE_RATE, float32ToPcm16, resample, calculateVolume, createCaptureWorkletUrl } from '@/lib/audio';

function classifyMicError(err) {
  const name = err?.name || '';
  if (name === 'NotAllowedError') {
    return {
      type: 'denied',
      device: 'microphone',
      title: 'Microphone access blocked',
      message:
        'You previously blocked the microphone. Click the lock/camera icon in your browser\'s address bar, set Microphone to "Allow", then retry.',
    };
  }
  if (name === 'NotFoundError') {
    return {
      type: 'not_found',
      device: 'microphone',
      title: 'No microphone found',
      message: 'No microphone was detected. Connect a microphone and try again.',
    };
  }
  if (name === 'NotReadableError' || name === 'AbortError') {
    return {
      type: 'busy',
      device: 'microphone',
      title: 'Microphone unavailable',
      message: 'The microphone is already in use by another application. Close it and retry.',
    };
  }
  if (name === 'SecurityError') {
    return {
      type: 'security',
      device: 'microphone',
      title: 'Insecure context',
      message: 'Microphone access requires HTTPS. Open the app over a secure connection.',
    };
  }
  return {
    type: 'unknown',
    device: 'microphone',
    title: 'Microphone error',
    message: err?.message || 'An unexpected error occurred.',
  };
}

export function useAudioCapture({ onAudioData } = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [volume, setVolume] = useState(0);
  const [permissionError, setPermissionError] = useState(null);
  const ctxRef = useRef(null);
  const workletRef = useRef(null);
  const streamRef = useRef(null);

  const clearError = useCallback(() => setPermissionError(null), []);

  const startRecording = useCallback(async () => {
    // Clear any previous error on retry
    setPermissionError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: CAPTURE_SAMPLE_RATE },
      });
      streamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE });
      ctxRef.current = ctx;

      const workletUrl = createCaptureWorkletUrl();
      await ctx.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

      const source = ctx.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(ctx, 'capture-processor');
      workletRef.current = worklet;

      worklet.port.onmessage = (e) => {
        const float32 = e.data;
        // Resample if browser didn't honor our sampleRate request
        const resampled = ctx.sampleRate !== CAPTURE_SAMPLE_RATE
          ? resample(float32, ctx.sampleRate, CAPTURE_SAMPLE_RATE)
          : float32;
        const pcm16 = float32ToPcm16(resampled);
        setVolume(calculateVolume(pcm16));
        onAudioData?.(pcm16);
      };

      source.connect(worklet);
      worklet.connect(ctx.destination); // needed for processing to continue
      setIsRecording(true);
    } catch (err) {
      setPermissionError(classifyMicError(err));
      setIsRecording(false);
    }
  }, [onAudioData]);

  const stopRecording = useCallback(() => {
    workletRef.current?.disconnect();
    ctxRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    workletRef.current = null;
    ctxRef.current = null;
    streamRef.current = null;
    setIsRecording(false);
    setVolume(0);
  }, []);

  return { startRecording, stopRecording, isRecording, volume, permissionError, clearError };
}
