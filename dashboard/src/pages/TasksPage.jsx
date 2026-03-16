/**
 * Page: TasksPage — Dedicated page for managing Planned Tasks and Scheduled/Cron tasks.
 *
 * Two tabs:
 *   1. Planned Tasks — AI-decomposed multi-step task pipelines (from TaskPanel)
 *   2. Scheduled Tasks — Cron/recurring tasks managed via scheduler service
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { cn } from '@/lib/cn';
import {
    ListTodo, Clock, Play, Pause, Trash2, RefreshCw, CheckCircle2,
    AlertCircle, Loader2, X, Eye, Calendar, Repeat, Pencil,
    ChevronRight, ChevronDown, Zap, MoreVertical, Plus, History,
} from 'lucide-react';
import HumanInputCard from '@/components/chat/HumanInputCard';

// ── Planned Task Constants ───────────────────────────────────────────

const STATUS_CONFIG = {
    pending: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Pending' },
    planning: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/10', label: 'Planning...' },
    awaiting_confirmation: { icon: ListTodo, color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Review Plan' },
    running: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/10', label: 'Running' },
    paused: { icon: Pause, color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Paused' },
    completed: { icon: CheckCircle2, color: 'text-green-400', bg: 'bg-green-500/10', label: 'Completed' },
    failed: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-500/10', label: 'Failed' },
    cancelled: { icon: X, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Cancelled' },
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

const SCHED_STATUS_CONFIG = {
    active: { icon: Play, color: 'text-green-400', bg: 'bg-green-500/10', label: 'Active' },
    paused: { icon: Pause, color: 'text-amber-400', bg: 'bg-amber-500/10', label: 'Paused' },
    completed: { icon: CheckCircle2, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Completed' },
    failed: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-500/10', label: 'Failed' },
};

// ── Step Timeline (reused from TaskPanel pattern) ────────────────────

function StepTimeline({ step, isLast }) {
    const status = STEP_STATUS[step.status] || STEP_STATUS.pending;
    const persona = PERSONA_LABELS[step.persona_id] || { label: step.persona_id, color: 'bg-muted text-muted-foreground' };
    return (
        <div className="flex gap-3">
            <div className="flex flex-col items-center">
                <div className={cn('h-2.5 w-2.5 rounded-full shrink-0 mt-1.5 ring-2 ring-offset-1 ring-offset-background', status.dot,
                    step.status === 'completed' ? 'ring-green-500/20' : step.status === 'running' ? 'ring-blue-500/30' : 'ring-transparent'
                )} />
                {!isLast && <div className={cn('w-0.5 flex-1 min-h-6 mt-1', status.line)} />}
            </div>
            <div className="flex-1 min-w-0 pb-3">
                <div className="flex items-start gap-2">
                    <p className={cn('text-sm font-medium leading-tight flex-1',
                        step.status === 'completed' && 'text-muted-foreground',
                        step.status === 'skipped' && 'text-muted-foreground/50 line-through',
                    )}>{step.title}</p>
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full shrink-0 font-medium', persona.color)}>
                        {persona.label}
                    </span>
                </div>
                {step.status === 'running' && (
                    <p className="text-xs text-blue-500 mt-0.5 flex items-center gap-1">
                        <Loader2 className="h-3 w-3 animate-spin" /> Executing...
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

// ── Planned Task Detail ──────────────────────────────────────────────

function PlannedTaskDetail({ task, onBack }) {
    const allPendingInputs = useTaskStore((s) => s.pendingInputs);
    const pendingInputs = useMemo(
        () => Object.values(allPendingInputs).filter((i) => i.taskId === task.id),
        [allPendingInputs, task.id],
    );
    const [expanded, setExpanded] = useState(true);

    const handleAction = useCallback(async (action) => {
        try { await api.post(`/tasks/${task.id}/action`, { action }); } catch (err) { console.error(err); }
    }, [task.id]);

    const handleExecute = useCallback(async () => {
        try { await api.post(`/tasks/${task.id}/execute`); } catch (err) { console.error(err); }
    }, [task.id]);

    const handleRetry = useCallback(async () => {
        try { await api.post(`/tasks/${task.id}/retry`); } catch (err) { console.error(err); }
    }, [task.id]);

    const handleDelete = useCallback(async () => {
        try {
            await api.delete(`/tasks/${task.id}`);
            useTaskStore.getState().removeTask(task.id);
            onBack();
        } catch (err) { console.error(err); }
    }, [task.id, onBack]);

    const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
    const Icon = config.icon;

    return (
        <div className="space-y-4">
            <button onClick={onBack} className="flex items-center gap-1 text-xs text-primary hover:underline">
                ← Back to all tasks
            </button>
            <div className="rounded-xl border border-border p-5">
                <div className="flex items-start gap-3">
                    <Icon className={cn('h-5 w-5 shrink-0 mt-0.5', config.color, config.icon === Loader2 && 'animate-spin')} />
                    <div className="flex-1 min-w-0">
                        <h3 className="text-base font-semibold">{task.title || 'Untitled Task'}</h3>
                        <p className="text-sm text-muted-foreground mt-1">{task.description}</p>
                    </div>
                    <span className={cn('text-xs px-2.5 py-1 rounded-full font-medium shrink-0', config.bg, config.color)}>
                        {config.label}
                    </span>
                </div>
                {(task.status === 'running' || task.status === 'planning') && (
                    <div className="mt-3 h-2 w-full rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full bg-blue-500 transition-all duration-700"
                            style={{ width: `${Math.max(task.progress ?? 0, 5)}%` }} />
                    </div>
                )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 flex-wrap">
                {task.status === 'awaiting_confirmation' && (
                    <button onClick={handleExecute}
                        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
                        <Play className="h-3.5 w-3.5" /> Execute Plan
                    </button>
                )}
                {task.status === 'running' && (
                    <button onClick={() => handleAction('pause')}
                        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition-colors">
                        <Pause className="h-3.5 w-3.5" /> Pause
                    </button>
                )}
                {task.status === 'paused' && (
                    <button onClick={() => handleAction('resume')}
                        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors">
                        <Play className="h-3.5 w-3.5" /> Resume
                    </button>
                )}
                {['running', 'paused', 'awaiting_confirmation'].includes(task.status) && (
                    <button onClick={() => handleAction('cancel')}
                        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors">
                        <X className="h-3.5 w-3.5" /> Cancel
                    </button>
                )}
                {(task.status === 'failed' || task.status === 'cancelled') && (
                    <button onClick={handleRetry}
                        className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors">
                        <RefreshCw className="h-3.5 w-3.5" /> Retry Failed Steps
                    </button>
                )}
                <button onClick={handleDelete}
                    className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg text-red-500 hover:bg-red-500/10 transition-colors ml-auto">
                    <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
            </div>

            {/* Pending Inputs */}
            {pendingInputs.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-amber-400 flex items-center gap-1">
                        <Zap className="h-3 w-3" /> Waiting for Input
                    </h4>
                    {pendingInputs.map((input) => <HumanInputCard key={input.id} input={input} taskId={task.id} />)}
                </div>
            )}

            {/* Steps */}
            {(task.steps || []).length > 0 && (
                <div className="rounded-xl border border-border p-4">
                    <button onClick={() => setExpanded(!expanded)}
                        className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground w-full mb-3">
                        <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-90')} />
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
                <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4">
                    <p className="text-xs font-medium text-green-400 mb-1 flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Result
                    </p>
                    <p className="text-sm whitespace-pre-wrap text-green-300">{task.result_summary}</p>
                </div>
            )}

            {/* Metadata */}
            <div className="text-xs text-muted-foreground space-x-3">
                {task.created_at && <span>Created: {new Date(task.created_at).toLocaleString()}</span>}
                {task.updated_at && <span>Updated: {new Date(task.updated_at).toLocaleString()}</span>}
            </div>
        </div>
    );
}

// ── Planned Tasks Tab ────────────────────────────────────────────────

function PlannedTasksTab() {
    const rawTasks = useTaskStore((s) => s.tasks);
    const tasks = useMemo(
        () => Object.values(rawTasks).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
        [rawTasks],
    );
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState(null);
    const [filter, setFilter] = useState('all');

    useEffect(() => {
        setLoading(true);
        api.get('/tasks').then((data) => {
            if (data?.tasks) data.tasks.forEach((t) => useTaskStore.getState().setTask(t));
        }).catch(() => { }).finally(() => setLoading(false));
    }, []);

    const filtered = useMemo(() => {
        if (filter === 'all') return tasks;
        if (filter === 'active') return tasks.filter(t => ['running', 'paused', 'planning', 'awaiting_confirmation'].includes(t.status));
        return tasks.filter(t => t.status === filter);
    }, [tasks, filter]);

    const selectedTask = selected ? rawTasks[selected] : null;

    if (selectedTask) {
        return <PlannedTaskDetail task={selectedTask} onBack={() => setSelected(null)} />;
    }

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex gap-2 flex-wrap">
                {[
                    { key: 'all', label: 'All' },
                    { key: 'active', label: 'Active' },
                    { key: 'completed', label: 'Completed' },
                    { key: 'failed', label: 'Failed' },
                ].map(({ key, label }) => (
                    <button key={key} onClick={() => setFilter(key)}
                        className={cn(
                            'text-xs px-3 py-1.5 rounded-full font-medium transition-colors',
                            filter === key ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted',
                        )}>
                        {label} {key === 'all' ? `(${tasks.length})` : ''}
                    </button>
                ))}
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <ListTodo className="h-10 w-10 text-muted-foreground/40 mb-3" />
                    <p className="text-sm text-muted-foreground">No planned tasks yet</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">
                        Ask Omni to plan a complex task via voice or chat
                    </p>
                </div>
            ) : (
                <div className="grid gap-3">
                    {filtered.map((task) => {
                        const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
                        const Icon = config.icon;
                        const stepCount = (task.steps || []).length;
                        const completedSteps = (task.steps || []).filter(s => s.status === 'completed').length;

                        return (
                            <div key={task.id} onClick={() => setSelected(task.id)}
                                className="rounded-xl border border-border p-4 hover:bg-accent/50 transition-colors cursor-pointer group">
                                <div className="flex items-center gap-3">
                                    <Icon className={cn('h-5 w-5 shrink-0', config.color, config.icon === Loader2 && 'animate-spin')} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">{task.title || task.description?.slice(0, 80)}</p>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium', config.bg, config.color)}>
                                                {config.label}
                                            </span>
                                            {stepCount > 0 && (
                                                <span className="text-xs text-muted-foreground">{completedSteps}/{stepCount} steps</span>
                                            )}
                                            {task.created_at && (
                                                <span className="text-[10px] text-muted-foreground/60 ml-auto">
                                                    {new Date(task.created_at).toLocaleDateString()}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                                </div>
                                {(task.status === 'running' || task.status === 'planning') && (
                                    <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                                        <div className="h-full rounded-full bg-blue-500 transition-all duration-700"
                                            style={{ width: `${Math.max(task.progress ?? 0, 5)}%` }} />
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ── Execution History Modal ──────────────────────────────────────────

function ExecutionHistoryModal({ taskId, taskDesc, onClose }) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get(`/scheduled-tasks/${taskId}/history?limit=20`)
            .then((data) => setHistory(data?.executions || []))
            .catch(() => { })
            .finally(() => setLoading(false));
    }, [taskId]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
            <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[70vh] overflow-hidden flex flex-col"
                onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between px-5 py-3 border-b border-border">
                    <div>
                        <h3 className="text-sm font-semibold">Execution History</h3>
                        <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[350px]">{taskDesc}</p>
                    </div>
                    <button onClick={onClose} className="rounded-md p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                    {loading ? (
                        <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                    ) : history.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-8">No executions yet</p>
                    ) : (
                        <div className="space-y-2">
                            {history.map((exec) => (
                                <div key={exec.id} className="rounded-lg border border-border p-3">
                                    <div className="flex items-center gap-2">
                                        {exec.status === 'success' ? (
                                            <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />
                                        ) : exec.status === 'failed' ? (
                                            <AlertCircle className="h-3.5 w-3.5 text-red-400" />
                                        ) : (
                                            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                                        )}
                                        <span className="text-xs font-medium capitalize">{exec.status}</span>
                                        {exec.started_at && (
                                            <span className="text-[10px] text-muted-foreground ml-auto">
                                                {new Date(exec.started_at).toLocaleString()}
                                            </span>
                                        )}
                                    </div>
                                    {exec.result && (
                                        <p className="text-xs text-muted-foreground mt-1.5 line-clamp-3">{exec.result}</p>
                                    )}
                                    {exec.error && (
                                        <p className="text-xs text-red-400 mt-1.5">{exec.error}</p>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ── Scheduled Tasks Tab ──────────────────────────────────────────────

function ScheduledTasksTab() {
    const [tasks, setTasks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [historyTask, setHistoryTask] = useState(null);
    const [filter, setFilter] = useState('all');

    const loadTasks = useCallback(() => {
        setLoading(true);
        api.get('/scheduled-tasks')
            .then((data) => setTasks(data?.tasks || []))
            .catch(() => { })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { loadTasks(); }, [loadTasks]);

    const handleAction = useCallback(async (taskId, action) => {
        try {
            await api.post(`/scheduled-tasks/${taskId}/action`, { action });
            loadTasks();
        } catch (err) { console.error(err); }
    }, [loadTasks]);

    const handleDelete = useCallback(async (taskId) => {
        try {
            await api.delete(`/scheduled-tasks/${taskId}`);
            setTasks((prev) => prev.filter((t) => t.id !== taskId));
        } catch (err) { console.error(err); }
    }, []);

    const filtered = useMemo(() => {
        if (filter === 'all') return tasks;
        return tasks.filter((t) => t.status === filter);
    }, [tasks, filter]);

    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex gap-2 flex-wrap">
                {[
                    { key: 'all', label: 'All' },
                    { key: 'active', label: 'Active' },
                    { key: 'paused', label: 'Paused' },
                    { key: 'failed', label: 'Failed' },
                ].map(({ key, label }) => (
                    <button key={key} onClick={() => setFilter(key)}
                        className={cn(
                            'text-xs px-3 py-1.5 rounded-full font-medium transition-colors',
                            filter === key ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted',
                        )}>
                        {label} {key === 'all' ? `(${tasks.length})` : ''}
                    </button>
                ))}
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
            ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Calendar className="h-10 w-10 text-muted-foreground/40 mb-3" />
                    <p className="text-sm text-muted-foreground">No scheduled tasks</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">
                        Ask Omni to schedule a recurring task, e.g. "Send me a daily news summary every morning"
                    </p>
                </div>
            ) : (
                <div className="grid gap-3">
                    {filtered.map((task) => {
                        const cfg = SCHED_STATUS_CONFIG[task.status] || SCHED_STATUS_CONFIG.active;
                        const StatusIcon = cfg.icon;
                        return (
                            <div key={task.id} className="rounded-xl border border-border p-4 hover:bg-accent/30 transition-colors">
                                <div className="flex items-start gap-3">
                                    <StatusIcon className={cn('h-5 w-5 shrink-0 mt-0.5', cfg.color)} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium">{task.description}</p>
                                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                                            <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium', cfg.bg, cfg.color)}>
                                                {cfg.label}
                                            </span>
                                            <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-400 font-medium">
                                                <Repeat className="h-2.5 w-2.5" /> {task.schedule}
                                            </span>
                                            {task.run_count > 0 && (
                                                <span className="text-[10px] text-muted-foreground">
                                                    {task.run_count} run{task.run_count !== 1 ? 's' : ''}
                                                    {task.fail_count > 0 && `, ${task.fail_count} failed`}
                                                </span>
                                            )}
                                            {task.last_run_at && (
                                                <span className="text-[10px] text-muted-foreground/60 ml-auto">
                                                    Last: {new Date(task.last_run_at).toLocaleString()}
                                                </span>
                                            )}
                                        </div>
                                        {task.last_result && (
                                            <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 bg-muted/30 rounded px-2 py-1">
                                                {task.last_result}
                                            </p>
                                        )}
                                        {task.consecutive_failures > 0 && (
                                            <p className="text-xs text-red-400 mt-1 flex items-center gap-1">
                                                <AlertCircle className="h-3 w-3" />
                                                {task.consecutive_failures} consecutive failure{task.consecutive_failures > 1 ? 's' : ''}
                                            </p>
                                        )}
                                    </div>
                                </div>

                                {/* Actions */}
                                <div className="flex items-center gap-2 mt-3 pt-2 border-t border-border/50">
                                    {task.status === 'active' && (
                                        <button onClick={() => handleAction(task.id, 'pause')}
                                            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors">
                                            <Pause className="h-3 w-3" /> Pause
                                        </button>
                                    )}
                                    {task.status === 'paused' && (
                                        <button onClick={() => handleAction(task.id, 'resume')}
                                            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors">
                                            <Play className="h-3 w-3" /> Resume
                                        </button>
                                    )}
                                    <button onClick={() => setHistoryTask(task)}
                                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
                                        <History className="h-3 w-3" /> History
                                    </button>
                                    <button onClick={() => handleDelete(task.id)}
                                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md text-red-500 hover:bg-red-500/10 transition-colors ml-auto">
                                        <Trash2 className="h-3 w-3" /> Delete
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {historyTask && (
                <ExecutionHistoryModal
                    taskId={historyTask.id}
                    taskDesc={historyTask.description}
                    onClose={() => setHistoryTask(null)}
                />
            )}
        </div>
    );
}

// ── Main Page ────────────────────────────────────────────────────────

export default function TasksPage() {
    useDocumentTitle('Tasks');
    const [tab, setTab] = useState('planned');

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">Tasks</h1>
            </div>

            {/* Tab Switcher */}
            <div className="flex gap-1 border-b border-border">
                <button onClick={() => setTab('planned')}
                    className={cn(
                        'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
                        tab === 'planned'
                            ? 'border-primary text-primary'
                            : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}>
                    <ListTodo className="h-4 w-4" /> Planned Tasks
                </button>
                <button onClick={() => setTab('scheduled')}
                    className={cn(
                        'flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
                        tab === 'scheduled'
                            ? 'border-primary text-primary'
                            : 'border-transparent text-muted-foreground hover:text-foreground',
                    )}>
                    <Calendar className="h-4 w-4" /> Scheduled Tasks
                </button>
            </div>

            {/* Tab Content */}
            {tab === 'planned' ? <PlannedTasksTab /> : <ScheduledTasksTab />}
        </div>
    );
}
