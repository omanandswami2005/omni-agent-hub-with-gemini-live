/**
 * Chat: TypingIndicator — Animated dots when agent is processing.
 */

export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 p-2">
      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
    </div>
  );
}
