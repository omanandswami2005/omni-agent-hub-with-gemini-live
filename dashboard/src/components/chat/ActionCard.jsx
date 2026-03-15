/**
 * Chat: ActionCard — Compact collapsible card for tool calls, MCP invocations,
 * agent transfers, cross-device actions, and image generation.
 *
 * Renders collapsed by default with icon + label + status badge.
 * Expanding reveals arguments, response, timing, and source info.
 */

import { useState } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { cn } from '@/lib/cn';
import {
  Wrench,
  Plug,
  Monitor,
  ArrowRightLeft,
  Image,
  CheckCircle,
  XCircle,
  Loader2,
  ChevronRight,
  Cpu,
} from 'lucide-react';

const KIND_CONFIG = {
  tool: { icon: Wrench, color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Tool' },
  mcp: { icon: Plug, color: 'text-violet-500', bg: 'bg-violet-500/10', label: 'MCP' },
  native_plugin: { icon: Cpu, color: 'text-emerald-500', bg: 'bg-emerald-500/10', label: 'Plugin' },
  cross_device: {
    icon: Monitor,
    color: 'text-orange-500',
    bg: 'bg-orange-500/10',
    label: 'Device',
  },
  agent_transfer: {
    icon: ArrowRightLeft,
    color: 'text-indigo-500',
    bg: 'bg-indigo-500/10',
    label: 'Transfer',
  },
  image_gen: { icon: Image, color: 'text-pink-500', bg: 'bg-pink-500/10', label: 'Image Gen' },
};

function StatusIndicator({ status }) {
  if (status === 'loading') {
    return <Loader2 size={12} className="animate-spin text-amber-500" />;
  }
  if (status === 'success') {
    return <CheckCircle size={12} className="text-green-500" />;
  }
  if (status === 'error') {
    return <XCircle size={12} className="text-red-500" />;
  }
  return null;
}

function formatToolName(name) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function truncate(str, maxLen = 120) {
  if (!str || str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '…';
}

export default function ActionCard({ action }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!action) return null;

  const {
    type,
    tool_name,
    arguments: args,
    result,
    success,
    action_kind,
    source_label,
    to_agent,
    message: transferMessage,
  } = action;

  const isTransfer = type === 'agent_transfer';
  const kind = isTransfer ? 'agent_transfer' : action_kind || 'tool';
  const config = KIND_CONFIG[kind] || KIND_CONFIG.tool;
  const Icon = config.icon;

  // Determine status
  const hasResponse = action.responded;
  const status = hasResponse ? (success === false ? 'error' : 'success') : 'loading';

  // Display name
  const displayName = isTransfer ? `→ ${to_agent || 'Agent'}` : formatToolName(tool_name || '');

  const sourceText = source_label || config.label;

  return (
    <div className="group relative my-1.5 ml-9 max-w-[80%]">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex w-full items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition-all',
          'border-border/50 hover:border-border hover:bg-muted/30',
          isOpen && 'bg-muted/20',
        )}
      >
        {/* Kind icon */}
        <div className={cn('flex h-5 w-5 items-center justify-center rounded', config.bg)}>
          <Icon size={11} className={config.color} />
        </div>

        {/* Label */}
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <span className="text-foreground/80 truncate text-xs font-medium">{displayName}</span>
          {sourceText && (
            <span className="text-muted-foreground shrink-0 text-[10px]">{sourceText}</span>
          )}
        </div>

        {/* Status + expand */}
        <div className="flex items-center gap-1.5">
          <StatusIndicator status={status} />
          <ChevronRight
            size={12}
            className={cn('text-muted-foreground/50 transition-transform', isOpen && 'rotate-90')}
          />
        </div>
      </button>
      {status === 'loading' && !isTransfer && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            // Mark cancelled in UI — pass call_id for exact match
            useChatStore.getState().completeAction(tool_name, {
              result: 'Cancelled by user',
              success: false,
            }, action.call_id);
            useChatStore.getState().setToolActive(tool_name, false);
            // Send custom event so the ChatPanel/VoiceProvider can send the abort text
            window.dispatchEvent(new CustomEvent('cancel_tool', { detail: { tool_name, call_id: action.call_id } }));
          }}
          className="text-destructive hover:text-destructive/80 bg-destructive/10 absolute top-1.5 -right-2 inline-flex translate-x-full items-center rounded-full px-2 py-0.5 text-[10px] opacity-0 transition-colors group-hover:opacity-100"
          title="Cancel Execution"
        >
          <XCircle size={10} className="mr-1" />
          Cancel
        </button>
      )}

      {/* Expanded details */}
      {isOpen && (
        <div className="border-border/40 mt-1 ml-3 space-y-1.5 border-l-2 pb-1 pl-3">
          {/* Transfer message */}
          {isTransfer && transferMessage && (
            <p className="text-muted-foreground text-[11px]">{truncate(transferMessage, 200)}</p>
          )}

          {/* Arguments */}
          {args != null && typeof args === 'object' && (
            <div>
              <p className="text-muted-foreground/70 text-[10px] font-medium tracking-wider uppercase">
                Arguments
              </p>
              <div className="bg-muted/40 mt-0.5 rounded px-2 py-1">
                {Object.keys(args).length > 0 ? (
                  Object.entries(args).map(([k, v]) => (
                    <div key={k} className="flex gap-2 text-[11px]">
                      <span className="text-muted-foreground shrink-0 font-medium">{k}:</span>
                      <span className="text-foreground/70 min-w-0 break-all">
                        {typeof v === 'string' ? truncate(v) : truncate(JSON.stringify(v))}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-muted-foreground text-[11px] italic">
                    No arguments provided
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Response */}
          {hasResponse && result && (
            <div>
              <p className="text-muted-foreground/70 text-[10px] font-medium tracking-wider uppercase">
                Result
              </p>
              <p className="bg-muted/40 text-foreground/70 mt-0.5 line-clamp-4 rounded px-2 py-1 text-[11px]">
                {truncate(result, 300)}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
