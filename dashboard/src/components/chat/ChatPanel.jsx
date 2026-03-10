/**
 * Chat: ChatPanel — Main chat interface with message list, input, and voice orb.
 */

import { useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import MessageBubble from '@/components/chat/MessageBubble';
import ChatInput from '@/components/chat/ChatInput';
import VoiceOrb from '@/components/chat/VoiceOrb';
import TranscriptLine from '@/components/chat/TranscriptLine';
import TypingIndicator from '@/components/chat/TypingIndicator';

export default function ChatPanel({ onSend, onToggleRecording, isRecording, captureVolume, playbackVolume }) {
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

  const orbState = isRecording ? 'listening' : agentState;

  return (
    <div className="flex h-full flex-col">
      {/* Message list */}
      <div ref={listRef} className="flex-1 space-y-1 overflow-y-auto p-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {agentState === 'processing' && <TypingIndicator />}
      </div>

      {/* Live transcript */}
      {(transcript.input || transcript.output) && (
        <div className="space-y-1 px-4 pb-2">
          {transcript.input && <TranscriptLine text={transcript.input} isFinal={false} />}
          {transcript.output && <TranscriptLine text={transcript.output} isFinal />}
        </div>
      )}

      {/* Voice orb */}
      <div className="flex items-center justify-center py-4">
        <VoiceOrb
          state={orbState}
          onToggle={onToggleRecording}
          captureVolume={captureVolume}
          playbackVolume={playbackVolume}
        />
      </div>

      {/* Text input */}
      <div className="border-t border-border p-4">
        <ChatInput onSend={onSend} disabled={agentState === 'speaking'} />
      </div>
    </div>
  );
}
