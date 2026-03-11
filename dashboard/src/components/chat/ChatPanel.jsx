/**
 * Chat: ChatPanel — Main chat interface with message list and text input.
 * Voice orb is now a global overlay (FloatingVoiceBubble) — not in this panel.
 */

import { useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import MessageBubble from '@/components/chat/MessageBubble';
import ChatInput from '@/components/chat/ChatInput';
import TranscriptLine from '@/components/chat/TranscriptLine';
import TypingIndicator from '@/components/chat/TypingIndicator';
import { Mic } from 'lucide-react';

export default function ChatPanel({ onSend, isRecording, captureVolume, playbackVolume }) {
  const messages = useChatStore((s) => s.messages);
  const agentState = useChatStore((s) => s.agentState);
  const transcript = useChatStore((s) => s.transcript);
  const listRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, transcript]);

  return (
    <div className="flex h-full flex-col rounded-xl border border-border/40 bg-background/50 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-3">
        <h2 className="text-sm font-semibold">Conversation</h2>
        {isRecording && (
          <div className="flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-1 text-xs text-red-500">
            <Mic size={12} className="animate-pulse" />
            Listening
          </div>
        )}
      </div>

      {/* Message list */}
      <div ref={listRef} className="flex-1 space-y-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <div className="rounded-full bg-muted/50 p-4">
              <Mic size={24} />
            </div>
            <p className="text-sm">Start speaking or type a message</p>
            <p className="text-xs text-muted-foreground/70">Your conversation will appear here</p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {agentState === 'processing' && <TypingIndicator />}
      </div>

      {/* Live transcript overlay */}
      {(transcript.input || transcript.output) && (
        <div className="border-t border-border/30 bg-muted/20 px-4 py-2 space-y-1">
          {transcript.input && (
            <TranscriptLine text={transcript.input} isFinal={false} direction="input" />
          )}
          {transcript.output && (
            <TranscriptLine text={transcript.output} isFinal direction="output" />
          )}
        </div>
      )}

      {/* Text input */}
      <div className="border-t border-border/40 p-3">
        <ChatInput onSend={onSend} disabled={agentState === 'speaking'} />
      </div>
    </div>
  );
}
