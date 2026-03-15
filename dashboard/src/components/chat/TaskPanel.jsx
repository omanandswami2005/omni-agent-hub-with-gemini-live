/**
 * TaskPanel — Live task planning progress sidebar panel.
 *
 * Shows planned tasks with step-by-step progress, status badges,
 * and human-in-the-loop input cards. Replaces PipelineMonitor for
 * the new Planned Task system.
 */

import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { ListTodo, Play, Pause, X, ChevronRight, Clock, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import HumanInputCard from './HumanInputCard';
import { useCallback, useEffect } from 'react';

const STATUS_CONFIG = {
    pending: { icon: Clock, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Pending' },
    planning: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-500/10', label: 'Planning...' },
    awaiting_confirmation: { icon: ListTodo, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-500/10', label: 'Review Plan' },
    running: { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-500/10', label: 'Running' },
    paused: { icon: Pause, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-500/10', label: 'Paused' },
    completed: { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50 dark:bg-green-500/10', label: 'Completed' },
    failed: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-500/10', label: 'Failed' },
    cancelled: { icon: X, color: 'text-muted-foreground', bg: 'bg-muted/30', label: 'Cancelled' },
};

const STEP_ICONS = {
    pending: '○',
    running: '◉',
    awaiting_input: '◈',
    completed: '●',
    failed: '✕',
    skipped: '⊘',
};

const STEP_COLORS = {
    pending: 'text-muted-foreground',
    running: 'text-blue-500',
    awaiting_input: 'text-amber-500',
    completed: 'text-green-500',
    failed: 'text-red-500',
    skipped: 'text-muted-foreground/50',
};

function StepItem({ step }) {
    const icon = STEP_ICONS[step.status] || '○';
    const color = STEP_COLORS[step.status] || '';

    return (
        <div className="flex items-start gap-2 py-1.5">
            <span className={cn('text-sm mt-0.5 font-mono', color)}>{icon}</span>
            <div className="flex-1 min-w-0">
                <p className={cn('text-sm', step.status === 'completed' && 'line-through opacity-60')}>
                    {step.title}
                </p>
                <p className="text-xs text-muted-foreground">
                    {step.persona_id}
                    {step.status === 'running' && <span className="ml-1 animate-pulse">●</span>}
                </p>
                {step.output && step.status === 'completed' && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{step.output}</p>
                )}
                {step.error && (
                    <p className="text-xs text-red-500 mt-1">{step.error}</p>
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
                'w-full text-left rounded-lg border p-3 transition-colors',
                isActive ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50',
            )}
        >
            <div className="flex items-center gap-2">
                <Icon className={cn('h-4 w-4 shrink-0', config.color, config.icon === Loader2 && 'animate-spin')} />
                <p className="text-sm font-medium truncate flex-1">{task.title || task.description?.slice(0, 60)}</p>
                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            </div>
            <div className="flex items-center gap-2 mt-1.5">
                <span className={cn('text-xs px-1.5 py-0.5 rounded', config.bg, config.color)}>
                    {config.label}
                </span>
                {stepCount > 0 && (
                    <span className="text-xs text-muted-foreground">
                        {completedSteps}/{stepCount} steps
                    </span>
                )}
            </div>
            {task.status === 'running' && (
                <div className="mt-2 h-1 w-full rounded-full bg-muted overflow-hidden">
                    <div
                        className="h-full rounded-full bg-blue-500 transition-all duration-500"
                        style={{ width: `${Math.max(progress, 3)}%` }}
                    />
                </div>
            )}
        </button>
    );
}

function TaskDetail({ task }) {
    const pendingInputs = useTaskStore((s) => s.getInputsForTask(task.id));

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

    return (
        <div className="space-y-3">
            {/* Header */}
            <div>
                <h3 className="text-sm font-semibold">{task.title || 'Untitled Task'}</h3>
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{task.description}</p>
                <div className="flex items-center gap-2 mt-2">
                    <span className={cn('text-xs px-2 py-0.5 rounded-full', config.bg, config.color)}>
                        {config.label}
                    </span>
                    {task.progress != null && (
                        <span className="text-xs text-muted-foreground">{Math.round(task.progress)}%</span>
                    )}
                </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2">
                {task.status === 'awaiting_confirmation' && (
                    <button
                        onClick={handleExecute}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
                    >
                        <Play className="h-3 w-3" /> Execute
                    </button>
                )}
                {task.status === 'running' && (
                    <button
                        onClick={() => handleAction('pause')}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-amber-500 text-white hover:bg-amber-600"
                    >
                        <Pause className="h-3 w-3" /> Pause
                    </button>
                )}
                {task.status === 'paused' && (
                    <button
                        onClick={() => handleAction('resume')}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-blue-500 text-white hover:bg-blue-600"
                    >
                        <Play className="h-3 w-3" /> Resume
                    </button>
                )}
                {['running', 'paused', 'awaiting_confirmation'].includes(task.status) && (
                    <button
                        onClick={() => handleAction('cancel')}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-red-500/10 text-red-500 hover:bg-red-500/20"
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

            {/* Steps */}
            {(task.steps || []).length > 0 && (
                <div className="border-t pt-2">
                    <p className="text-xs font-medium text-muted-foreground mb-1">Steps</p>
                    <div className="divide-y divide-border/50">
                        {task.steps.map((step) => (
                            <StepItem key={step.id} step={step} />
                        ))}
                    </div>
                </div>
            )}

            {/* Result summary */}
            {task.result_summary && (
                <div className="border-t pt-2">
                    <p className="text-xs font-medium text-muted-foreground mb-1">Result</p>
                    <p className="text-sm whitespace-pre-wrap">{task.result_summary}</p>
                </div>
            )}
        </div>
    );
}

export default function TaskPanel() {
    const tasks = useTaskStore((s) => s.getTaskList());
    const activeTaskId = useTaskStore((s) => s.activeTaskId);
    const setActiveTask = useTaskStore((s) => s.setActiveTask);
    const isPanelOpen = useTaskStore((s) => s.isPanelOpen);

    const activeTask = tasks.find((t) => t.id === activeTaskId);

    // Auto-load tasks on mount
    useEffect(() => {
        api.get('/tasks').then((data) => {
            if (data?.tasks) {
                data.tasks.forEach((t) => useTaskStore.getState().setTask(t));
            }
        }).catch(() => { });
    }, []);

    if (!isPanelOpen && tasks.length === 0) return null;

    return (
        <div className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                    <ListTodo className="h-4 w-4 text-muted-foreground" />
                    <p className="text-xs font-medium text-muted-foreground">Planned Tasks</p>
                </div>
                <span className="text-xs text-muted-foreground">
                    {tasks.filter((t) => t.status === 'running').length} running
                </span>
            </div>

            {activeTask ? (
                <div>
                    <button
                        onClick={() => useTaskStore.getState().setActiveTask(null)}
                        className="text-xs text-primary hover:underline mb-2"
                    >
                        ← All tasks
                    </button>
                    <TaskDetail task={activeTask} />
                </div>
            ) : (
                <div className="space-y-2">
                    {tasks.length === 0 ? (
                        <p className="text-xs text-muted-foreground py-2">
                            No tasks yet. Ask the agent to plan a complex task.
                        </p>
                    ) : (
                        tasks.slice(0, 10).map((task) => (
                            <TaskCard
                                key={task.id}
                                task={task}
                                isActive={task.id === activeTaskId}
                                onClick={() => setActiveTask(task.id)}
                            />
                        ))
                    )}
                </div>
            )}
        </div>
    );
}
