/**
 * useAudioCapture — Mic → AudioWorklet → PCM16 16kHz → callback.
 */

import { useRef, useState, useCallback } from 'react';
import { CAPTURE_SAMPLE_RATE, float32ToPcm16, resample, calculateVolume, createCaptureWorkletUrl } from '@/lib/audio';

export function useAudioCapture({ onAudioData } = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [volume, setVolume] = useState(0);
  const ctxRef = useRef(null);
  const workletRef = useRef(null);
  const streamRef = useRef(null);

  const startRecording = useCallback(async () => {
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
    } catch {
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

  return { startRecording, stopRecording, isRecording, volume };
}
