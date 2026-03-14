/**
 * useAudioPlayback — Queue-based PCM16 playback at 24kHz.
 */

import { useRef, useState, useCallback, useEffect } from 'react';
import { PLAYBACK_SAMPLE_RATE, pcm16ToFloat32, calculateVolume } from '@/lib/audio';
import { useChatStore } from '@/stores/chatStore';

export function useAudioPlayback() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [volume, setVolume] = useState(0);
  const ctxRef = useRef(null);
  const scheduledEnd = useRef(0);
  const playingRef = useRef(false);

  const getContext = useCallback(() => {
    if (!ctxRef.current || ctxRef.current.state === 'closed') {
      ctxRef.current = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE });
    }
    if (ctxRef.current.state === 'suspended') {
      ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  const enqueueAudio = useCallback(
    (pcm16Buffer) => {
      const ctx = getContext();
      const float32 = pcm16ToFloat32(pcm16Buffer);
      const audioBuffer = ctx.createBuffer(1, float32.length, PLAYBACK_SAMPLE_RATE);
      audioBuffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      const now = ctx.currentTime;
      const startAt = Math.max(now, scheduledEnd.current);
      source.start(startAt);
      scheduledEnd.current = startAt + audioBuffer.duration;

      source.onended = () => {
        if (ctx.currentTime >= scheduledEnd.current - 0.05) {
          setIsPlaying(false);
          playingRef.current = false;
          setVolume(0);
        }
      };

      setIsPlaying(true);
      playingRef.current = true;
      setVolume(calculateVolume(pcm16Buffer));
    },
    [getContext],
  );

  const stopPlayback = useCallback(() => {
    if (ctxRef.current && ctxRef.current.state !== 'closed') {
      ctxRef.current.close();
      ctxRef.current = null;
    }
    scheduledEnd.current = 0;
    setIsPlaying(false);
    playingRef.current = false;
    setVolume(0);
    // Clear any remaining items from the audio queue
    const store = useChatStore.getState();
    while (store.audioQueue.length > 0) {
      store.dequeueAudio();
    }
  }, []);

  // Stop playback immediately on interruption (agentState → 'listening')
  useEffect(() => {
    let prev = useChatStore.getState().agentState;
    const unsub = useChatStore.subscribe((state) => {
      if (state.agentState === 'listening' && prev !== 'listening') {
        // Agent was interrupted — kill all scheduled audio instantly
        if (ctxRef.current && ctxRef.current.state !== 'closed') {
          ctxRef.current.close();
          ctxRef.current = null;
        }
        scheduledEnd.current = 0;
        setIsPlaying(false);
        playingRef.current = false;
        setVolume(0);
      }
      prev = state.agentState;
    });
    return unsub;
  }, []);

  // Process audio queue from chatStore
  useEffect(() => {
    const unsub = useChatStore.subscribe((state) => {
      if (state.audioQueue.length > 0) {
        const chunk = state.audioQueue[0];
        state.dequeueAudio();
        enqueueAudio(chunk);
      }
    });
    return unsub;
  }, [enqueueAudio]);

  return { enqueueAudio, stopPlayback, isPlaying, volume };
}
