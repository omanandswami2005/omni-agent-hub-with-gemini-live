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

export default function ChatPanel({
  onSend,
  isRecording,
  captureVolume,
  playbackVolume,
  isChatConnected,
}) {
  const messages = useChatStore((s) => s.messages);
  const agentState = useChatStore((s) => s.agentState);
  const transcript = useChatStore((s) => s.transcript);
  const crossTranscript = useChatStore((s) => s.crossTranscript);
  const listRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, transcript, crossTranscript]);

  // Listen for tool cancellation custom events
  useEffect(() => {
    const handleCancel = (e) => {
      if (e.detail?.tool_name && onSend) {
        onSend(
          `[System]: User cancelled the execution of the tool ${e.detail.tool_name}. Stop waiting and proceed.`,
        );
      }
    };
    window.addEventListener('cancel_tool', handleCancel);
    return () => window.removeEventListener('cancel_tool', handleCancel);
  }, [onSend]);

  return (
    <div className="border-border/40 bg-background/50 flex h-full flex-col rounded-xl border backdrop-blur-sm">
      {/* Header */}
      <div className="border-border/40 flex items-center justify-between border-b px-4 py-3">
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
          <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-2">
            <div className="bg-muted/50 rounded-full p-4">
              <Mic size={24} />
            </div>
            <p className="text-sm">Start speaking or type a message</p>
            <p className="text-muted-foreground/70 text-xs">Your conversation will appear here</p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {agentState === 'processing' && <TypingIndicator />}
      </div>

      {/* Live transcript overlay — own device */}
      {(transcript.input || transcript.output) && (
        <div className="border-border/30 bg-muted/20 space-y-1 border-t px-4 py-2">
          {transcript.input && (
            <TranscriptLine text={transcript.input} isFinal={false} direction="input" />
          )}
          {transcript.output && (
            <TranscriptLine text={transcript.output} isFinal direction="output" />
          )}
        </div>
      )}
      {/* Live transcript overlay — other device */}
      {(crossTranscript.input || crossTranscript.output) && (
        <div className="border-border/30 bg-muted/10 space-y-1 border-t px-4 py-2">
          <p className="text-muted-foreground/50 mb-1 text-[10px] uppercase tracking-wide">other device</p>
          {crossTranscript.input && (
            <TranscriptLine text={crossTranscript.input} isFinal={false} direction="input" />
          )}
          {crossTranscript.output && (
            <TranscriptLine text={crossTranscript.output} isFinal direction="output" />
          )}
        </div>
      )}

      {/* Text input */}
      <div className="border-border/40 border-t p-3">
        <ChatInput
          onSend={onSend}
          disabled={agentState === 'speaking'}
          disconnected={!isChatConnected}
        />
      </div>
    </div>
  );
}
