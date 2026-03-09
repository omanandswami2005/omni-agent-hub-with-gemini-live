/**
 * Chat: MessageBubble — Individual message display (user/agent/tool/system).
 */

export default function MessageBubble({ message }) {
  const isUser = message?.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 ${
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        }`}
      >
        {message?.content}
      </div>
    </div>
  );
}
