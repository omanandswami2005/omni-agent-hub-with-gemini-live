/**
 * Chat: VoiceOrb — Animated central orb for voice interaction.
 * States: idle (breathe), listening (pulse), processing/thinking (spin), speaking (wave).
 */

import { cn } from '@/lib/cn';

const STATE_STYLES = {
  idle: 'animate-[breathe_4s_ease-in-out_infinite] bg-primary/80',
  listening: 'animate-[pulse_1.2s_ease-in-out_infinite] bg-red-500 shadow-[0_0_40px_rgba(239,68,68,0.5)]',
  processing: 'animate-spin bg-amber-500',
  thinking: 'animate-spin bg-amber-500',
  speaking: 'animate-[wave_1s_ease-in-out_infinite] bg-green-500 shadow-[0_0_30px_rgba(34,197,94,0.4)]',
};

const STATE_LABELS = {
  idle: 'Start',
  listening: 'Listening…',
  processing: 'Thinking…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
};

export default function VoiceOrb({ state = 'idle', onToggle, captureVolume = 0, playbackVolume = 0 }) {
  const volume = state === 'listening' ? captureVolume : state === 'speaking' ? playbackVolume : 0;
  const ringScale = 1 + volume * 0.4;

  return (
    <div className="relative flex items-center justify-center">
      {/* Dynamic volume ring */}
      <div
        className={cn(
          'absolute rounded-full bg-primary/10 transition-transform duration-100',
          (state === 'listening' || state === 'speaking') && 'opacity-100',
        )}
        style={{
          width: '7rem',
          height: '7rem',
          transform: `scale(${ringScale})`,
          opacity: volume > 0.01 ? 0.6 : 0,
        }}
      />

      {/* Main orb button */}
      <button
        onClick={onToggle}
        className={cn(
          'relative z-10 flex h-24 w-24 items-center justify-center rounded-full transition-all duration-300 hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          STATE_STYLES[state] || STATE_STYLES.idle,
        )}
        aria-label={`Voice interaction — ${STATE_LABELS[state] || state}`}
      >
        <span className="text-sm font-medium text-white select-none">
          {STATE_LABELS[state] || state}
        </span>
      </button>
    </div>
  );
}
