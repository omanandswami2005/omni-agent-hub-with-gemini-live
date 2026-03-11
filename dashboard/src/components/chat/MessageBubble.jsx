/**
 * Chat: MessageBubble — Renders user, assistant, and system messages.
 * Supports: text, voice transcription, genui, images, tool calls/responses.
 */

import { lazy, Suspense } from 'react';
import { cn } from '@/lib/cn';
import { Mic, Bot, Wrench, CheckCircle, XCircle } from 'lucide-react';

const GenUIRenderer = lazy(() => import('@/components/genui/GenUIRenderer'));

export default function MessageBubble({ message }) {
  if (!message) return null;
  const { role, type, content, content_type, source } = message;

  // ── Tool call / response (system messages) ─────────────────────
  if (type === 'tool_call') return <ToolCallBubble message={message} />;
  if (type === 'tool_response') return <ToolResponseBubble message={message} />;

  const isUser = role === 'user';
  const isVoice = source === 'voice';

  return (
    <div className={cn('flex mb-3 group', isUser ? 'justify-end' : 'justify-start')}>
      {/* Avatar */}
      {!isUser && (
        <div className="mr-2 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot size={14} />
        </div>
      )}

      <div className={cn('max-w-[80%] space-y-2')}>
        {/* Source badge */}
        {isVoice && (
          <span className={cn(
            'inline-flex items-center gap-1 text-[10px] text-muted-foreground',
            isUser ? 'float-right' : '',
          )}>
            <Mic size={10} /> voice
          </span>
        )}

        {/* Text content */}
        {content && content_type !== 'genui' && (
          <div
            className={cn(
              'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
              isUser
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted/60 backdrop-blur-sm border border-border/40',
            )}
          >
            {content}
          </div>
        )}

        {/* GenUI block — inline in chat */}
        {message.genui_type && message.genui_data && (
          <div className="rounded-xl border border-border/60 bg-background p-3 shadow-sm">
            <Suspense fallback={<div className="h-20 animate-pulse rounded bg-muted" />}>
              <GenUIRenderer type={message.genui_type} data={message.genui_data} />
            </Suspense>
          </div>
        )}

        {/* Image content */}
        {content_type === 'image' && message.image_url && (
          <img
            src={message.image_url}
            alt="Shared image"
            className="max-h-64 rounded-xl border border-border/40 object-cover"
          />
        )}

        {/* Timestamp */}
        <p className={cn(
          'text-[10px] text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100',
          isUser ? 'text-right' : 'text-left',
        )}>
          {message.timestamp ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
        </p>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="ml-2 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">
          U
        </div>
      )}
    </div>
  );
}

function ToolCallBubble({ message }) {
  return (
    <div className="my-2 flex items-start gap-2 px-2">
      <Wrench size={14} className="mt-0.5 text-amber-500" />
      <div className="text-xs text-muted-foreground">
        <span className="font-medium text-amber-600">{message.tool_name}</span>
        {message.arguments && Object.keys(message.arguments).length > 0 && (
          <span className="ml-1 text-muted-foreground/70">
            ({Object.keys(message.arguments).join(', ')})
          </span>
        )}
      </div>
    </div>
  );
}

function ToolResponseBubble({ message }) {
  const Icon = message.success ? CheckCircle : XCircle;
  const color = message.success ? 'text-green-500' : 'text-red-500';
  return (
    <div className="my-2 flex items-start gap-2 px-2">
      <Icon size={14} className={cn('mt-0.5', color)} />
      <div className="max-w-[80%] text-xs text-muted-foreground">
        <span className="font-medium">{message.tool_name}</span>
        {message.content && (
          <p className="mt-0.5 line-clamp-3 text-muted-foreground/70">{message.content}</p>
        )}
      </div>
    </div>
  );
}
