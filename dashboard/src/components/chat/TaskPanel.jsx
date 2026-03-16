/**
 * TaskPanel — Full task lifecycle sidebar panel.
 *
 * Features: step timeline, Review Plan modal, edit/delete, lazy loading,
 * task categories, abort/restart support.
 */

import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import {
    ListTodo, Play, Pause, X, ChevronRight, ChevronLeft, Clock, CheckCircle2,
    AlertCircle, Loader2, Zap, RefreshCw, Trash2, Pencil, Eye,
    Calendar, Repeat, MoreVertical, ChevronDown,
} from 'lucide-react';
import HumanInputCard from './HumanInputCard';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// ── Constants ────────────────────────────────────────────────────────

const STATUS_CONFIG = {
    pending: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Pending', ring: 'ring-muted-foreground/30' },
    planning: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/10', label: 'Planning...', ring: 'ring-blue-500/30' },
    awaiting_confirmation: { icon: ListTodo, color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Review Plan', ring: 'ring-amber-500/30' },
    running: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/10', label: 'Running', ring: 'ring-blue-500/30' },
    paused: { icon: Pause, color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Paused', ring: 'ring-amber-500/30' },
    completed: { icon: CheckCircle2, color: 'text-green-400', bg: 'bg-green-500/10', label: 'Completed', ring: 'ring-green-500/30' },
    failed: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-500/10', label: 'Failed', ring: 'ring-red-500/30' },
    cancelled: { icon: X, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Cancelled', ring: 'ring-muted-foreground/30' },
};

const STEP_STATUS = {
    pending: { dot: 'bg-muted-foreground/30', line: 'bg-muted-foreground/20', text: 'text-muted-foreground' },
    running: { dot: 'bg-blue-500 animate-pulse', line: 'bg-blue-500/30', text: 'text-blue-500' },
    awaiting_input: { dot: 'bg-amber-500 animate-pulse', line: 'bg-amber-500/30', text: 'text-amber-500' },
    completed: { dot: 'bg-green-500', line: 'bg-green-500', text: 'text-green-500' },
    failed: { dot: 'bg-red-500', line: 'bg-red-500/30', text: 'text-red-500' },
    skipped: { dot: 'bg-muted-foreground/20', line: 'bg-muted-foreground/10', text: 'text-muted-foreground/50' },
};

const PERSONA_LABELS = {
    assistant: { label: 'Assistant', color: 'bg-white/5 text-foreground/70' },
    coder: { label: 'Coder', color: 'bg-violet-500/10 text-violet-300' },
    researcher: { label: 'Researcher', color: 'bg-cyan-500/10 text-cyan-300' },
    analyst: { label: 'Analyst', color: 'bg-orange-500/10 text-orange-300' },
    creative: { label: 'Creative', color: 'bg-pink-500/10 text-pink-300' },
};

const CATEGORIES = {
    all: { label: 'All', icon: ListTodo },
    running: { label: 'Active', icon: Loader2 },
    scheduled: { label: 'Scheduled', icon: Calendar },
    recurring: { label: 'Recurring', icon: Repeat },
    completed: { label: 'Completed', icon: CheckCircle2 },
    failed: { label: 'Failed', icon: AlertCircle },
};

const PAGE_SIZE = 10;

function categorizeTask(task) {
    if (task.status === 'running' || task.status === 'paused') return 'running';
    if (task.status === 'completed') return 'completed';
    if (task.status === 'failed') return 'failed';
    if (task.context?.scheduled || task.context?.cron_expression) return 'scheduled';
    if (task.context?.recurring) return 'recurring';
    return 'all';
}

// ── Step Timeline ────────────────────────────────────────────────────

function StepTimeline({ step, isLast }) {
    const status = STEP_STATUS[step.status] || STEP_STATUS.pending;
    const persona = PERSONA_LABELS[step.persona_id] || { label: step.persona_id, color: 'bg-muted text-muted-foreground' };

    return (
        <div className="flex gap-3 group">
            <div className="flex flex-col items-center">
                <div className={cn('h-2.5 w-2.5 rounded-full shrink-0 mt-1.5 ring-2 ring-offset-1 ring-offset-background transition-all', status.dot,
                    step.status === 'completed' ? 'ring-green-500/20' : step.status === 'running' ? 'ring-blue-500/30' : 'ring-transparent'
                )} />
                {!isLast && <div className={cn('w-0.5 flex-1 min-h-6 mt-1 transition-colors', status.line)} />}
            </div>
            <div className="flex-1 min-w-0 pb-3">
                <div className="flex items-start gap-2">
                    <p className={cn('text-sm font-medium leading-tight flex-1',
                        step.status === 'completed' && 'text-muted-foreground',
                        step.status === 'skipped' && 'text-muted-foreground/50 line-through',
                    )}>
                        {step.title}
                    </p>
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full shrink-0 font-medium', persona.color)}>
                        {persona.label}
                    </span>
                </div>
                {step.description && <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>}
                {step.status === 'running' && (
                    <p className="text-xs text-blue-500 mt-0.5 flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" /> Executing...
                    </p>
                )}
                {step.status === 'awaiting_input' && (
                    <p className="text-xs text-amber-500 mt-0.5 flex items-center gap-1">
                        <Zap className="h-3 w-3" /> Waiting for input
                    </p>
                )}
                {step.output && step.status === 'completed' && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2 bg-muted/30 rounded px-2 py-1">{step.output}</p>
                )}
                {step.error && (
                    <div className="mt-1 bg-red-500/10 rounded px-2 py-1.5">
                        <p className="text-xs text-red-400">{step.error}</p>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Review Plan Modal ────────────────────────────────────────────────

function ReviewPlanModal({ task, onClose, onExecute, onEdit, onDelete, onRetry }) {
    const [editMode, setEditMode] = useState(false);
    const [editText, setEditText] = useState(task.description);
    const [saving, setSaving] = useState(false);

    const handleSaveEdit = async () => {
        if (!editText.trim() || editText === task.description) {
            setEditMode(false);
            return;
        }
        setSaving(true);
        await onEdit(editText.trim());
        setSaving(false);
        setEditMode(false);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
            <div
                className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] overflow-hidden flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-3 border-b border-border">
                    <h3 className="text-sm font-semibold">Review Plan</h3>
                    <button onClick={onClose} className="rounded-md p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-5 space-y-4">
                    {/* Task description */}
                    <div>
                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Task Description</label>
                        {editMode ? (
                            <div className="space-y-2">
                                <textarea
                                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                                    rows={4}
                                    value={editText}
                                    onChange={(e) => setEditText(e.target.value)}
                                    autoFocus
                                />
                                <div className="flex gap-2 justify-end">
                                    <button
                                        onClick={() => { setEditMode(false); setEditText(task.description); }}
                                        className="text-xs px-3 py-1.5 rounded-md bg-muted hover:bg-muted/80 transition-colors"
                                    >Cancel</button>
                                    <button
                                        onClick={handleSaveEdit}
                                        disabled={saving}
                                        className="text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1"
                                    >
                                        {saving && <Loader2 className="h-3 w-3 animate-spin" />}
                                        Save & Re-plan
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div className="flex items-start gap-2">
                                <p className="text-sm flex-1 bg-muted/30 rounded-lg px-3 py-2">{task.description}</p>
                                {task.status !== 'running' && (
                                    <button onClick={() => setEditMode(true)} className="rounded-md p-1.5 hover:bg-muted shrink-0" title="Edit">
                                        <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                                    </button>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Title */}
                    {task.title && (
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-1 block">Generated Title</label>
                            <p className="text-sm font-medium">{task.title}</p>
                        </div>
                    )}

                    {/* Steps */}
                    {(task.steps || []).length > 0 && (
                        <div>
                            <label className="text-xs font-medium text-muted-foreground mb-2 block">
                                Planned Steps ({task.steps.length})
                            </label>
                            <div className="pl-1">
                                {task.steps.map((step, i) => (
                                    <StepTimeline key={step.id} step={step} isLast={i === task.steps.length - 1} />
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Metadata */}
                    <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                        {task.created_at && <span>Created: {new Date(task.created_at).toLocaleString()}</span>}
                        {task.updated_at && <span> · Updated: {new Date(task.updated_at).toLocaleString()}</span>}
                    </div>

                    {/* Validation Warnings */}
                    {task.context?.validation && (task.context.validation.warnings?.length > 0 || task.context.validation.blockers?.length > 0) && (
                        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1.5">
                            <p className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                                <AlertCircle className="h-3.5 w-3.5" /> Pre-flight Resource Check
                            </p>
                            {(task.context.validation.blockers || []).map((b, i) => (
                                <p key={`b-${i}`} className="text-xs text-red-400 flex items-start gap-1.5">
                                    <X className="h-3 w-3 mt-0.5 shrink-0" /> {b}
                                </p>
                            ))}
                            {(task.context.validation.warnings || []).map((w, i) => (
                                <p key={`w-${i}`} className="text-xs text-amber-300 flex items-start gap-1.5">
                                    <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" /> {w}
                                </p>
                            ))}
                        </div>
                    )}
                </div>

                {/* Footer actions */}
                <div className="flex items-center justify-between px-5 py-3 border-t border-border bg-muted/20">
                    <button
                        onClick={onDelete}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md text-red-500 hover:bg-red-500/10 transition-colors"
                    >
                        <Trash2 className="h-3 w-3" /> Delete
                    </button>
                    <div className="flex gap-2">
                        <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-md bg-muted hover:bg-muted/80 transition-colors">
                            Close
                        </button>
                        {task.status === 'awaiting_confirmation' && (
                            <button
                                onClick={onExecute}
                                className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                            >
                                <Play className="h-3 w-3" /> Execute Plan
                            </button>
                        )}
                        {(task.status === 'failed' || task.status === 'cancelled') && (
                            <>
                                <button
                                    onClick={onRetry}
                                    className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors"
                                >
                                    <RefreshCw className="h-3 w-3" /> Retry Failed
                                </button>
                                <button
                                    onClick={() => { setEditMode(true); }}
                                    className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                                >
                                    <Pencil className="h-3 w-3" /> Edit & Retry
                                </button>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── Task Card ────────────────────────────────────────────────────────

function TaskCard({ task, isActive, onClick, onReview, onDelete }) {
    const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
    const Icon = config.icon;
    const progress = task.progress ?? 0;
    const stepCount = (task.steps || []).length;
    const completedSteps = (task.steps || []).filter((s) => s.status === 'completed').length;
    const [showMenu, setShowMenu] = useState(false);
    const menuRef = useRef(null);

    useEffect(() => {
        if (!showMenu) return;
        const handler = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setShowMenu(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [showMenu]);

    return (
        <div
            className={cn(
                'w-full text-left rounded-xl border p-3 transition-all duration-200 relative group',
                isActive ? 'border-white/[0.12] bg-white/[0.04] shadow-sm' : 'border-white/[0.06] hover:bg-white/[0.03] hover:border-white/[0.10]',
            )}
        >
            <div className="flex items-center gap-2 cursor-pointer" onClick={onClick}>
                <Icon className={cn('h-4 w-4 shrink-0', config.color, config.icon === Loader2 && 'animate-spin')} />
                <p className="text-sm font-medium truncate flex-1">{task.title || task.description?.slice(0, 60)}</p>

                {/* Context menu */}
                <div className="relative shrink-0" ref={menuRef}>
                    <button
                        onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu); }}
                        className="rounded p-0.5 hover:bg-muted opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                        <MoreVertical className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                    {showMenu && (
                        <div className="absolute right-0 top-5 z-10 rounded-lg border border-border bg-card shadow-lg py-1 w-32">
                            <button
                                onClick={(e) => { e.stopPropagation(); setShowMenu(false); onReview(); }}
                                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-muted"
                            >
                                <Eye className="h-3 w-3" /> View Plan
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); setShowMenu(false); onDelete(); }}
                                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs hover:bg-muted text-red-500"
                            >
                                <Trash2 className="h-3 w-3" /> Delete
                            </button>
                        </div>
                    )}
                </div>
            </div>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium', config.bg, config.color)}>
                    {config.label}
                </span>
                {stepCount > 0 && (
                    <span className="text-xs text-muted-foreground">
                        {completedSteps}/{stepCount} steps
                    </span>
                )}
                {task.context?.cron_expression && (
                    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-400 font-medium">
                        <Repeat className="h-2.5 w-2.5" /> Cron
                    </span>
                )}
                {task.context?.scheduled && (
                    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-medium">
                        <Calendar className="h-2.5 w-2.5" /> Scheduled
                    </span>
                )}
                {task.context?.reminder && (
                    <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 font-medium">
                        <Clock className="h-2.5 w-2.5" /> Reminder
                    </span>
                )}
                {task.created_at && (
                    <span className="text-[10px] text-muted-foreground/60 ml-auto">
                        {new Date(task.created_at).toLocaleDateString()}
                    </span>
                )}
            </div>
            {(task.status === 'running' || task.status === 'planning') && (
                <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                    <div
                        className="h-full rounded-full bg-blue-500 transition-all duration-700 ease-out"
                        style={{ width: `${Math.max(progress, task.status === 'planning' ? 15 : 3)}%` }}
                    />
                </div>
            )}
            {/* Quick action: Review Plan button for awaiting_confirmation */}
            {task.status === 'awaiting_confirmation' && (
                <button
                    onClick={(e) => { e.stopPropagation(); onReview(); }}
                    className="mt-2 w-full flex items-center justify-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 transition-colors font-medium"
                >
                    <Eye className="h-3 w-3" /> Review Plan
                </button>
            )}
        </div>
    );
}

// ── Task Detail (shown when clicking into a task) ────────────────────

function TaskDetail({ task, onOpenReview }) {
    const allPendingInputs = useTaskStore((s) => s.pendingInputs);
    const pendingInputs = useMemo(() => Object.values(allPendingInputs).filter((i) => i.taskId === task.id), [allPendingInputs, task.id]);
    const [expanded, setExpanded] = useState(true);

    const handleAction = useCallback(async (action) => {
        try {
            await api.post(`/tasks/${task.id}/action`, { action });
        } catch (err) {
            console.error('Task action failed:', err);
        }
    }, [task.id]);

    const handleExecute = useCallback(async () => {
        try {
            await api.post(`/tasks/${task.id}/execute`);
        } catch (err) {
            console.error('Task execute failed:', err);
        }
    }, [task.id]);

    const handleRetry = useCallback(async () => {
        try {
            await api.post(`/tasks/${task.id}/retry`);
        } catch (err) {
            console.error('Task retry failed:', err);
        }
    }, [task.id]);

    const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
    const Icon = config.icon;

    return (
        <div className="space-y-3">
            {/* Header */}
            <div className="rounded-lg border border-border p-3">
                <div className="flex items-start gap-2">
                    <Icon className={cn('h-5 w-5 shrink-0 mt-0.5', config.color, config.icon === Loader2 && 'animate-spin')} />
                    <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold leading-tight">{task.title || 'Untitled Task'}</h3>
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{task.description}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 mt-2">
                    <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium', config.bg, config.color)}>
                        {config.label}
                    </span>
                    {task.progress != null && task.status === 'running' && (
                        <span className="text-xs text-muted-foreground">{Math.round(task.progress)}%</span>
                    )}
                </div>
                {(task.status === 'running' || task.status === 'planning') && (
                    <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full bg-blue-500 transition-all duration-700 ease-out"
                            style={{ width: `${Math.max(task.progress ?? 0, 5)}%` }} />
                    </div>
                )}
            </div>

            {/* Validation Warnings */}
            {task.context?.validation && (task.context.validation.warnings?.length > 0 || task.context.validation.blockers?.length > 0) && (
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1">
                    <p className="text-xs font-medium text-amber-400 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> Resource Check
                    </p>
                    {(task.context.validation.blockers || []).map((b, i) => (
                        <p key={`b-${i}`} className="text-xs text-red-400 flex items-start gap-1.5">
                            <X className="h-3 w-3 mt-0.5 shrink-0" /> {b}
                        </p>
                    ))}
                    {(task.context.validation.warnings || []).map((w, i) => (
                        <p key={`w-${i}`} className="text-xs text-amber-300 flex items-start gap-1.5">
                            <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" /> {w}
                        </p>
                    ))}
                </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 flex-wrap">
                {task.status === 'awaiting_confirmation' && (
                    <>
                        <button
                            onClick={onOpenReview}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 transition-colors"
                        >
                            <Eye className="h-3 w-3" /> Review Plan
                        </button>
                        <button
                            onClick={handleExecute}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                        >
                            <Play className="h-3 w-3" /> Execute
                        </button>
                    </>
                )}
                {task.status === 'running' && (
                    <button onClick={() => handleAction('pause')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-500 text-white hover:bg-amber-600 transition-colors">
                        <Pause className="h-3 w-3" /> Pause
                    </button>
                )}
                {task.status === 'paused' && (
                    <button onClick={() => handleAction('resume')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors">
                        <Play className="h-3 w-3" /> Resume
                    </button>
                )}
                {['running', 'paused', 'awaiting_confirmation'].includes(task.status) && (
                    <button onClick={() => handleAction('cancel')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors">
                        <X className="h-3 w-3" /> Cancel
                    </button>
                )}
                {(task.status === 'failed' || task.status === 'cancelled') && (
                    <>
                        <button onClick={() => handleRetry()}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors">
                            <RefreshCw className="h-3 w-3" /> Retry Failed Steps
                        </button>
                        <button onClick={onOpenReview}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
                            <Pencil className="h-3 w-3" /> Edit & Retry
                        </button>
                    </>
                )}
            </div>

            {/* Pending Inputs */}
            {pendingInputs.length > 0 && (
                <div className="space-y-2">
                    {pendingInputs.map((input) => <HumanInputCard key={input.id} input={input} taskId={task.id} />)}
                </div>
            )}

            {/* Steps */}
            {(task.steps || []).length > 0 && (
                <div>
                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors mb-2 w-full"
                    >
                        <ChevronRight className={cn('h-3 w-3 transition-transform', expanded && 'rotate-90')} />
                        Steps ({(task.steps || []).filter(s => s.status === 'completed').length}/{task.steps.length})
                    </button>
                    {expanded && (
                        <div className="pl-1">
                            {task.steps.map((step, i) => (
                                <StepTimeline key={step.id} step={step} isLast={i === task.steps.length - 1} />
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Result */}
            {task.result_summary && task.status === 'completed' && (
                <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-3">
                    <p className="text-xs font-medium text-green-400 mb-1 flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Result
                    </p>
                    <p className="text-sm whitespace-pre-wrap text-green-300">{task.result_summary}</p>
                </div>
            )}
            {task.result_summary && task.status === 'failed' && (
                <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3">
                    <p className="text-xs font-medium text-red-400 mb-1 flex items-center gap-1">
                        <AlertCircle className="h-3 w-3" /> Error Summary
                    </p>
                    <p className="text-sm whitespace-pre-wrap text-red-300">{task.result_summary}</p>
                </div>
            )}
        </div>
    );
}

// ── Category Filter Tabs ─────────────────────────────────────────────

function CategoryTabs({ active, counts, onChange }) {
    return (
        <div className="flex gap-1 overflow-x-auto scrollbar-none pb-1">
            {Object.entries(CATEGORIES).map(([key, { label, icon: CatIcon }]) => {
                const count = counts[key] || 0;
                if (key !== 'all' && count === 0) return null;
                return (
                    <button
                        key={key}
                        onClick={() => onChange(key)}
                        className={cn(
                            'flex items-center gap-1 text-[10px] px-2 py-1 rounded-full whitespace-nowrap transition-colors font-medium',
                            active === key ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted',
                        )}
                    >
                        <CatIcon className="h-2.5 w-2.5" />
                        {label} {count > 0 && `(${count})`}
                    </button>
                );
            })}
        </div>
    );
}

// ── Main Panel ───────────────────────────────────────────────────────

export default function TaskPanel() {
    const rawTasks = useTaskStore((s) => s.tasks);
    const tasks = useMemo(() => Object.values(rawTasks).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')), [rawTasks]);
    const activeTaskId = useTaskStore((s) => s.activeTaskId);
    const setActiveTask = useTaskStore((s) => s.setActiveTask);

    const [reviewTask, setReviewTask] = useState(null);
    const [category, setCategory] = useState('all');
    const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
    const [loading, setLoading] = useState(false);

    const activeTask = tasks.find((t) => t.id === activeTaskId);
    const runningCount = tasks.filter((t) => t.status === 'running').length;
    const pendingInputCount = Object.keys(useTaskStore.getState().pendingInputs).length;

    // Category counts
    const categoryCounts = useMemo(() => {
        const counts = { all: tasks.length, running: 0, scheduled: 0, recurring: 0, completed: 0, failed: 0 };
        tasks.forEach((t) => {
            const cat = categorizeTask(t);
            if (cat !== 'all') counts[cat] = (counts[cat] || 0) + 1;
        });
        return counts;
    }, [tasks]);

    // Filtered + paginated
    const filteredTasks = useMemo(() => {
        if (category === 'all') return tasks;
        return tasks.filter((t) => categorizeTask(t) === category);
    }, [tasks, category]);
    const visibleTasks = filteredTasks.slice(0, visibleCount);
    const hasMore = filteredTasks.length > visibleCount;

    // Load tasks on mount
    useEffect(() => {
        setLoading(true);
        api.get('/tasks').then((data) => {
            if (data?.tasks) {
                data.tasks.forEach((t) => useTaskStore.getState().setTask(t));
            }
        }).catch(() => { }).finally(() => setLoading(false));
    }, []);

    // Reset pagination when category changes
    useEffect(() => { setVisibleCount(PAGE_SIZE); }, [category]);

    // Keep reviewTask in sync with store updates
    useEffect(() => {
        if (reviewTask) {
            const updated = rawTasks[reviewTask.id];
            if (updated) setReviewTask(updated);
        }
    }, [rawTasks, reviewTask?.id]);

    const handleDelete = useCallback(async (taskId) => {
        try {
            await api.delete(`/tasks/${taskId}`);
            useTaskStore.getState().removeTask(taskId);
            if (reviewTask?.id === taskId) setReviewTask(null);
            if (activeTaskId === taskId) useTaskStore.getState().setActiveTask(null);
        } catch (err) {
            console.error('Delete failed:', err);
        }
    }, [reviewTask, activeTaskId]);

    const handleEdit = useCallback(async (taskId, newDescription) => {
        try {
            const result = await api.put(`/tasks/${taskId}`, { description: newDescription });
            if (result) {
                useTaskStore.getState().setTask(result);
            }
        } catch (err) {
            console.error('Edit failed:', err);
        }
    }, []);

    const handleExecute = useCallback(async (taskId) => {
        try {
            await api.post(`/tasks/${taskId}/execute`);
            setReviewTask(null);
        } catch (err) {
            console.error('Execute failed:', err);
        }
    }, []);

    const handleRetry = useCallback(async (taskId) => {
        try {
            await api.post(`/tasks/${taskId}/retry`);
            setReviewTask(null);
        } catch (err) {
            console.error('Retry failed:', err);
        }
    }, []);

    if (tasks.length === 0 && !loading) return null;

    return (
        <div className="rounded-xl border border-white/[0.06] bg-card/50 backdrop-blur-sm">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.06]">
                <div className="flex items-center gap-1.5">
                    <ListTodo className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-semibold text-foreground">Tasks</p>
                </div>
                <div className="flex items-center gap-2">
                    {pendingInputCount > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-500 font-medium">
                            {pendingInputCount} input{pendingInputCount > 1 ? 's' : ''}
                        </span>
                    )}
                    {runningCount > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-500 font-medium flex items-center gap-1">
                            <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                            {runningCount} running
                        </span>
                    )}
                </div>
            </div>

            {/* Categories */}
            {tasks.length > 3 && (
                <div className="px-3 pt-2">
                    <CategoryTabs active={category} counts={categoryCounts} onChange={setCategory} />
                </div>
            )}

            <div className="p-3">
                {loading && tasks.length === 0 ? (
                    <div className="flex items-center justify-center py-6">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                ) : activeTask ? (
                    <div>
                        <button
                            onClick={() => useTaskStore.getState().setActiveTask(null)}
                            className="flex items-center gap-1 text-xs text-primary hover:underline mb-3"
                        >
                            <ChevronLeft className="h-3 w-3" /> All tasks
                        </button>
                        <TaskDetail
                            task={activeTask}
                            onOpenReview={() => setReviewTask(activeTask)}
                        />
                    </div>
                ) : (
                    <div className="space-y-2">
                        {visibleTasks.map((task) => (
                            <TaskCard
                                key={task.id}
                                task={task}
                                isActive={task.id === activeTaskId}
                                onClick={() => setActiveTask(task.id)}
                                onReview={() => setReviewTask(task)}
                                onDelete={() => handleDelete(task.id)}
                            />
                        ))}
                        {hasMore && (
                            <button
                                onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                                className="w-full text-xs text-primary hover:underline text-center py-2 flex items-center justify-center gap-1"
                            >
                                <ChevronDown className="h-3 w-3" />
                                Show {Math.min(PAGE_SIZE, filteredTasks.length - visibleCount)} more
                                ({filteredTasks.length - visibleCount} remaining)
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* Review Plan Modal */}
            {reviewTask && (
                <ReviewPlanModal
                    task={reviewTask}
                    onClose={() => setReviewTask(null)}
                    onExecute={() => handleExecute(reviewTask.id)}
                    onEdit={(desc) => handleEdit(reviewTask.id, desc)}
                    onDelete={() => handleDelete(reviewTask.id)}
                    onRetry={() => handleRetry(reviewTask.id)}
                />
            )}
        </div>
    );
}
