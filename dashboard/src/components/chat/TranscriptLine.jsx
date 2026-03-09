/**
 * Chat: TranscriptLine — Real-time speech transcript overlay.
 */

export default function TranscriptLine({ text, isFinal = false }) {
  return (
    <p className={`text-sm ${isFinal ? 'text-foreground' : 'text-muted-foreground italic'}`}>
      {text}
    </p>
  );
}
