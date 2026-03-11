/**
 * Chat: TranscriptLine — Real-time speech transcript overlay with direction indicator.
 */

import { Mic, Bot } from 'lucide-react';
import { cn } from '@/lib/cn';

export default function TranscriptLine({ text, isFinal = false, direction }) {
  const isInput = direction === 'input';
  return (
    <div className={cn('flex items-start gap-2 text-sm', isFinal ? '' : 'animate-pulse')}>
      {isInput ? (
        <Mic size={12} className="mt-0.5 flex-shrink-0 text-muted-foreground" />
      ) : (
        <Bot size={12} className="mt-0.5 flex-shrink-0 text-primary" />
      )}
      <p className={cn(
        isFinal ? 'text-foreground' : 'text-muted-foreground italic',
      )}>
        {text}
      </p>
    </div>
  );
}
