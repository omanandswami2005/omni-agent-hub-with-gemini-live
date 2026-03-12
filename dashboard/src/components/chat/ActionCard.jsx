/**
 * Chat: ActionCard — Compact collapsible card for tool calls, MCP invocations,
 * agent transfers, cross-device actions, and image generation.
 *
 * Renders collapsed by default with icon + label + status badge.
 * Expanding reveals arguments, response, timing, and source info.
 */

import { useState } from 'react';
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
    cross_device: { icon: Monitor, color: 'text-orange-500', bg: 'bg-orange-500/10', label: 'Device' },
    agent_transfer: { icon: ArrowRightLeft, color: 'text-indigo-500', bg: 'bg-indigo-500/10', label: 'Transfer' },
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

    const { type, tool_name, arguments: args, result, success, action_kind, source_label, to_agent, message: transferMessage } = action;

    const isTransfer = type === 'agent_transfer';
    const kind = isTransfer ? 'agent_transfer' : (action_kind || 'tool');
    const config = KIND_CONFIG[kind] || KIND_CONFIG.tool;
    const Icon = config.icon;

    // Determine status
    const hasResponse = action.responded;
    const status = hasResponse ? (success === false ? 'error' : 'success') : 'loading';

    // Display name
    const displayName = isTransfer
        ? `→ ${to_agent || 'Agent'}`
        : formatToolName(tool_name || '');

    const sourceText = source_label || config.label;

    return (
        <div className="my-1.5 ml-9">
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
                    <span className="truncate text-xs font-medium text-foreground/80">{displayName}</span>
                    {sourceText && (
                        <span className="shrink-0 text-[10px] text-muted-foreground">{sourceText}</span>
                    )}
                </div>

                {/* Status + expand */}
                <div className="flex items-center gap-1.5">
                    <StatusIndicator status={status} />
                    <ChevronRight
                        size={12}
                        className={cn(
                            'text-muted-foreground/50 transition-transform',
                            isOpen && 'rotate-90',
                        )}
                    />
                </div>
            </button>

            {/* Expanded details */}
            {isOpen && (
                <div className="ml-3 mt-1 space-y-1.5 border-l-2 border-border/40 pl-3 pb-1">
                    {/* Transfer message */}
                    {isTransfer && transferMessage && (
                        <p className="text-[11px] text-muted-foreground">{truncate(transferMessage, 200)}</p>
                    )}

                    {/* Arguments */}
                    {args && Object.keys(args).length > 0 && (
                        <div>
                            <p className="text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider">Arguments</p>
                            <div className="mt-0.5 rounded bg-muted/40 px-2 py-1">
                                {Object.entries(args).map(([k, v]) => (
                                    <div key={k} className="flex gap-2 text-[11px]">
                                        <span className="shrink-0 font-medium text-muted-foreground">{k}:</span>
                                        <span className="min-w-0 break-all text-foreground/70">
                                            {typeof v === 'string' ? truncate(v) : truncate(JSON.stringify(v))}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Response */}
                    {hasResponse && result && (
                        <div>
                            <p className="text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider">Result</p>
                            <p className="mt-0.5 rounded bg-muted/40 px-2 py-1 text-[11px] text-foreground/70 line-clamp-4">
                                {truncate(result, 300)}
                            </p>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
