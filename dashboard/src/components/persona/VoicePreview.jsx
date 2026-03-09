/**
 * Persona: VoicePreview — Preview Gemini voice options.
 */

// TODO: Implement:
//   - Play sample audio for each voice (Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr)
//   - Visual waveform during playback

const VOICES = ['Puck', 'Charon', 'Kore', 'Fenrir', 'Aoede', 'Leda', 'Orus', 'Zephyr'];

export default function VoicePreview({ selected, onSelect }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {VOICES.map((voice) => (
        <button
          key={voice}
          onClick={() => onSelect?.(voice)}
          className={`rounded-lg border px-3 py-2 text-sm ${
            selected === voice ? 'border-primary bg-primary/10' : 'border-border'
          }`}
        >
          {voice}
        </button>
      ))}
    </div>
  );
}
