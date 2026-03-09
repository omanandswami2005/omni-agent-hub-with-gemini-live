/**
 * Chat: ChatPanel — Main chat interface with message list, input, and voice orb.
 */

// TODO: Implement:
//   - Message list (auto-scroll to bottom)
//   - VoiceOrb (center, animated states)
//   - ChatInput (text fallback)
//   - TranscriptLine overlays
//   - Agent state visual indicators

export default function ChatPanel() {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto p-4">{/* Message list */}</div>
      <div className="flex items-center justify-center p-6">{/* VoiceOrb */}</div>
      <div className="border-t border-border p-4">{/* ChatInput */}</div>
    </div>
  );
}
