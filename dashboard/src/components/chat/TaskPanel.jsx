/**
 * TaskPanel — Live task planning progress sidebar panel.
 *
 * Shows planned tasks with step-by-step timeline progress, status badges,
 * and human-in-the-loop input cards. Primary task UI for the sidebar.
 */

import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { ListTodo, Play, Pause, X, ChevronRight, ChevronLeft, Clock, CheckCircle2, AlertCircle, Loader2, User, Zap, RefreshCw } from 'lucide-react';
import HumanInputCard from './HumanInputCard';
import { useCallback, useEffect, useState } from 'react';

const STATUS_CONFIG = {
    pending: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Pending', ring: 'ring-muted-foreground/30' },
    planning: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-500/10', label: 'Planning...', ring: 'ring-blue-500/30' },
    awaiting_confirmation: { icon: ListTodo, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-500/10', label: 'Review Plan', ring: 'ring-amber-500/30' },
    running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-500/10', label: 'Running', ring: 'ring-blue-500/30' },
    paused: { icon: Pause, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-500/10', label: 'Paused', ring: 'ring-amber-500/30' },
    completed: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-500/10', label: 'Completed', ring: 'ring-green-500/30' },
    failed: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-500/10', label: 'Failed', ring: 'ring-red-500/30' },
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
    assistant: { label: 'Assistant', color: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300' },
    coder: { label: 'Coder', color: 'bg-violet-100 text-violet-700 dark:bg-violet-700 dark:text-violet-300' },
    researcher: { label: 'Researcher', color: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-700 dark:text-cyan-300' },
    analyst: { label: 'Analyst', color: 'bg-orange-100 text-orange-700 dark:bg-orange-700 dark:text-orange-300' },
    creative: { label: 'Creative', color: 'bg-pink-100 text-pink-700 dark:bg-pink-700 dark:text-pink-300' },
};

function StepTimeline({ step, isLast }) {
    const status = STEP_STATUS[step.status] || STEP_STATUS.pending;
    const persona = PERSONA_LABELS[step.persona_id] || { label: step.persona_id, color: 'bg-muted text-muted-foreground' };

    return (
        <div className="flex gap-3 group">
            {/* Timeline connector */}
            <div className="flex flex-col items-center">
                <div className={cn('h-2.5 w-2.5 rounded-full shrink-0 mt-1.5 ring-2 ring-offset-1 ring-offset-background transition-all', status.dot,
                    step.status === 'completed' ? 'ring-green-500/20' : step.status === 'running' ? 'ring-blue-500/30' : 'ring-transparent'
                )} />
                {!isLast && (
                    <div className={cn('w-0.5 flex-1 min-h-6 mt-1 transition-colors', status.line)} />
                )}
            </div>

            {/* Step content */}
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
                    <p className="text-xs text-red-500 mt-1 bg-red-50 dark:bg-red-500/10 rounded px-2 py-1">{step.error}</p>
                )}
            </div>
        </div>
    );
}

function TaskCard({ task, isActive, onClick }) {
    const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
    const Icon = config.icon;
    const progress = task.progress ?? 0;
    const stepCount = (task.steps || []).length;
    const completedSteps = (task.steps || []).filter((s) => s.status === 'completed').length;

    return (
        <button
            onClick={onClick}
            className={cn(
                'w-full text-left rounded-lg border p-3 transition-all duration-200',
                isActive ? 'border-primary bg-primary/5 shadow-sm' : 'border-border hover:bg-muted/50 hover:border-muted-foreground/20',
            )}
        >
            <div className="flex items-center gap-2">
                <Icon className={cn('h-4 w-4 shrink-0', config.color, config.icon === Loader2 && 'animate-spin')} />
                <p className="text-sm font-medium truncate flex-1">{task.title || task.description?.slice(0, 60)}</p>
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            </div>
            <div className="flex items-center gap-2 mt-2">
                <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium', config.bg, config.color)}>
                    {config.label}
                </span>
                {stepCount > 0 && (
                    <span className="text-xs text-muted-foreground">
                        {completedSteps}/{stepCount} steps
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
        </button>
    );
}

function TaskDetail({ task }) {
    const pendingInputs = useTaskStore((s) => s.getInputsForTask(task.id));
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

    const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.pending;
    const Icon = config.icon;

    return (
        <div className="space-y-3">
            {/* Header with status */}
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
                        <div
                            className="h-full rounded-full bg-blue-500 transition-all duration-700 ease-out"
                            style={{ width: `${Math.max(task.progress ?? 0, 5)}%` }}
                        />
                    </div>
                )}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 flex-wrap">
                {task.status === 'awaiting_confirmation' && (
                    <button
                        onClick={handleExecute}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                    >
                        <Play className="h-3 w-3" /> Execute Plan
                    </button>
                )}
                {task.status === 'running' && (
                    <button
                        onClick={() => handleAction('pause')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-amber-500 text-white hover:bg-amber-600 transition-colors"
                    >
                        <Pause className="h-3 w-3" /> Pause
                    </button>
                )}
                {task.status === 'paused' && (
                    <button
                        onClick={() => handleAction('resume')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600 transition-colors"
                    >
                        <Play className="h-3 w-3" /> Resume
                    </button>
                )}
                {['running', 'paused', 'awaiting_confirmation'].includes(task.status) && (
                    <button
                        onClick={() => handleAction('cancel')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors"
                    >
                        <X className="h-3 w-3" /> Cancel
                    </button>
                )}
            </div>

            {/* Pending Input Requests */}
            {pendingInputs.length > 0 && (
                <div className="space-y-2">
                    {pendingInputs.map((input) => (
                        <HumanInputCard key={input.id} input={input} taskId={task.id} />
                    ))}
                </div>
            )}

            {/* Step Timeline */}
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

            {/* Result summary */}
            {task.result_summary && (
                <div className="rounded-lg border border-green-200 dark:border-green-500/20 bg-green-50 dark:bg-green-500/5 p-3">
                    <p className="text-xs font-medium text-green-700 dark:text-green-400 mb-1 flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Result
                    </p>
                    <p className="text-sm whitespace-pre-wrap text-green-800 dark:text-green-300">{task.result_summary}</p>
                </div>
            )}
        </div>
    );
}

export default function TaskPanel() {
    const tasks = useTaskStore((s) => s.getTaskList());
    const activeTaskId = useTaskStore((s) => s.activeTaskId);
    const setActiveTask = useTaskStore((s) => s.setActiveTask);

    const activeTask = tasks.find((t) => t.id === activeTaskId);
    const runningCount = tasks.filter((t) => t.status === 'running').length;
    const pendingInputCount = Object.keys(useTaskStore.getState().pendingInputs).length;

    // Auto-load tasks on mount
    useEffect(() => {
        api.get('/tasks').then((data) => {
            if (data?.tasks) {
                data.tasks.forEach((t) => useTaskStore.getState().setTask(t));
            }
        }).catch(() => { });
    }, []);

    if (tasks.length === 0) return null;

    return (
        <div className="rounded-lg border border-border bg-card">
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                <div className="flex items-center gap-1.5">
                    <ListTodo className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-semibold text-foreground">Planned Tasks</p>
                </div>
                <div className="flex items-center gap-2">
                    {pendingInputCount > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-500 font-medium">
                            {pendingInputCount} input{pendingInputCount > 1 ? 's' : ''} needed
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

            <div className="p-3">
                {activeTask ? (
                    <div>
                        <button
                            onClick={() => useTaskStore.getState().setActiveTask(null)}
                            className="flex items-center gap-1 text-xs text-primary hover:underline mb-3"
                        >
                            <ChevronLeft className="h-3 w-3" /> All tasks
                        </button>
                        <TaskDetail task={activeTask} />
                    </div>
                ) : (
                    <div className="space-y-2">
                        {tasks.slice(0, 10).map((task) => (
                            <TaskCard
                                key={task.id}
                                task={task}
                                isActive={task.id === activeTaskId}
                                onClick={() => setActiveTask(task.id)}
                            />
                        ))}
                        {tasks.length > 10 && (
                            <p className="text-xs text-muted-foreground text-center pt-1">
                                +{tasks.length - 10} more tasks
                            </p>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
