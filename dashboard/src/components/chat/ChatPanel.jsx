/**
 * Chat: ChatPanel — Main chat interface with message list and text input.
 * Voice orb is now a global overlay (FloatingVoiceBubble) — not in this panel.
 */

import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useChatStore } from '@/stores/chatStore';
import MessageBubble from '@/components/chat/MessageBubble';
import ChatInput from '@/components/chat/ChatInput';
import TranscriptLine from '@/components/chat/TranscriptLine';
import TypingIndicator from '@/components/chat/TypingIndicator';
import { Mic, ChevronUp } from 'lucide-react';

const PAGE_SIZE = 30;

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
  const sentinelRef = useRef(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const prevHeightRef = useRef(0);

  // Visible slice — always the latest N messages
  const visibleMessages = useMemo(
    () => messages.slice(-visibleCount),
    [messages, visibleCount],
  );
  const hasMore = messages.length > visibleCount;

  // Load more when scrolling to top (intersection observer on sentinel)
  useEffect(() => {
    const sentinel = sentinelRef.current;
    const list = listRef.current;
    if (!sentinel || !list) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && messages.length > visibleCount) {
          prevHeightRef.current = list.scrollHeight;
          setVisibleCount((v) => Math.min(v + PAGE_SIZE, messages.length));
        }
      },
      { root: list, threshold: 0.1 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [messages.length, visibleCount]);

  // Preserve scroll position after loading older messages
  useEffect(() => {
    const list = listRef.current;
    if (list && prevHeightRef.current > 0) {
      const newHeight = list.scrollHeight;
      list.scrollTop += newHeight - prevHeightRef.current;
      prevHeightRef.current = 0;
    }
  }, [visibleMessages.length]);

  // Auto-scroll to bottom on new messages (only if already near bottom)
  const isNearBottom = useRef(true);
  const onScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    isNearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  useEffect(() => {
    if (listRef.current && isNearBottom.current) {
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
    <div className="flex h-full flex-col rounded-2xl border border-white/[0.06] bg-card/50 backdrop-blur-xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">Conversation</h2>
        {isRecording && (
          <div className="flex items-center gap-1.5 rounded-full bg-red-500/10 px-2.5 py-1 text-xs text-red-400">
            <Mic size={12} className="animate-pulse" />
            Listening
          </div>
        )}
      </div>

      {/* Message list */}
      <div ref={listRef} onScroll={onScroll} className="flex-1 space-y-1 overflow-y-auto px-5 py-4">
        {messages.length === 0 && (
          <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-3">
            <div className="rounded-full border border-white/[0.06] bg-white/[0.03] p-5">
              <Mic size={24} className="text-foreground/40" />
            </div>
            <p className="text-sm font-medium text-foreground/60">Start speaking or type a message</p>
            <p className="text-xs text-muted-foreground/60">Your conversation will appear here</p>
          </div>
        )}
        {/* Sentinel for loading older messages */}
        {hasMore && (
          <div ref={sentinelRef} className="flex justify-center py-2">
            <span className="flex items-center gap-1 text-xs text-muted-foreground/50">
              <ChevronUp size={12} /> Scroll up for older messages
            </span>
          </div>
        )}
        {visibleMessages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {agentState === 'processing' && <TypingIndicator />}
      </div>

      {/* Live transcript overlay — own device */}
      {(transcript.input || transcript.output) && (
        <div className="border-t border-white/[0.04] bg-white/[0.02] space-y-1 px-5 py-2">
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
        <div className="border-t border-white/[0.04] bg-white/[0.01] space-y-1 px-5 py-2">
          <p className="text-muted-foreground/40 mb-1 text-[10px] uppercase tracking-widest">other device</p>
          {crossTranscript.input && (
            <TranscriptLine text={crossTranscript.input} isFinal={false} direction="input" />
          )}
          {crossTranscript.output && (
            <TranscriptLine text={crossTranscript.output} isFinal direction="output" />
          )}
        </div>
      )}

      {/* Text input */}
      <div className="border-t border-white/[0.06] p-3">
        <ChatInput
          onSend={onSend}
          disabled={agentState === 'speaking'}
          disconnected={!isChatConnected}
        />
      </div>
    </div>
  );
}
