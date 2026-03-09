/**
 * Chat: VoiceOrb — Animated central orb for voice interaction.
 */

// TODO: Implement:
//   - Pulsing animation when listening
//   - Waveform ring when speaking
//   - Spinning when thinking/tool_use
//   - Click to start/stop, hold for push-to-talk
//   - State from agentState in chatStore

export default function VoiceOrb({ state = 'idle', onToggle }) {
  return (
    <button
      onClick={onToggle}
      className="relative h-24 w-24 rounded-full bg-primary transition-all hover:scale-105"
      aria-label="Voice interaction"
    >
      <span className="text-primary-foreground text-sm">{state}</span>
    </button>
  );
}
