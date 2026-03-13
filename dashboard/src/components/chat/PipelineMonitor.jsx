/**
 * PipelineMonitor — Live task pipeline progress visualization.
 *
 * Shows the TaskArchitect DAG stages with real-time status updates.
 * Displayed in the DashboardPage right sidebar when a pipeline is active.
 */

import { cn } from '@/lib/cn';
import { usePipelineStore } from '@/stores/pipelineStore';

const STATUS_ICON = {
    pending: '⏳',
    running: '🔄',
    completed: '✅',
    failed: '❌',
};

const STATUS_COLORS = {
    pending: 'border-muted-foreground/30 bg-muted/20',
    running: 'border-blue-500 bg-blue-50 dark:bg-blue-500/10',
    completed: 'border-green-500 bg-green-50 dark:bg-green-500/10',
    failed: 'border-red-500 bg-red-50 dark:bg-red-500/10',
};

function StageCard({ stage, status }) {
    const s = status || { status: 'pending', progress: 0 };
    const icon = STATUS_ICON[s.status] || '❓';
    const color = STATUS_COLORS[s.status] || '';
    const progressPct = Math.round((s.progress || 0) * 100);

    return (
        <div className={cn('rounded-lg border-l-4 p-3', color)}>
            <div className="flex items-center gap-2">
                <span className="text-base">{icon}</span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{stage.name}</p>
                    <p className="text-xs text-muted-foreground">
                        {stage.stage_type} · {stage.tasks.length} task{stage.tasks.length !== 1 ? 's' : ''}
                    </p>
                </div>
            </div>

            {/* Task list */}
            <div className="mt-2 space-y-1">
                {stage.tasks.map((task) => (
                    <div key={task.id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
                        <span className="truncate">
                            [{task.persona_id}] {task.description}
                        </span>
                    </div>
                ))}
            </div>

            {/* Progress bar (when running) */}
            {s.status === 'running' && (
                <div className="mt-2">
                    <div className="h-1.5 w-full rounded-full bg-muted">
                        <div
                            className="h-1.5 rounded-full bg-blue-500 transition-all duration-300"
                            style={{ width: `${Math.max(progressPct, 5)}%` }}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}

export default function PipelineMonitor() {
    const pipeline = usePipelineStore((s) => s.pipeline);
    const stageStatus = usePipelineStore((s) => s.stageStatus);
    const history = usePipelineStore((s) => s.history);

    if (!pipeline && history.length === 0) return null;

    const stages = pipeline?.stages || [];
    const completedCount = stages.filter(
        (s) => stageStatus[s.name]?.status === 'completed'
    ).length;
    const totalCount = stages.length;

    return (
        <div className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-muted-foreground">Pipeline</p>
                {pipeline && (
                    <span className="text-xs text-muted-foreground">
                        {completedCount}/{totalCount} stages
                    </span>
                )}
            </div>

            {pipeline ? (
                <>
                    <p className="text-sm font-medium mb-1 truncate" title={pipeline.task_description}>
                        {pipeline.task_description}
                    </p>
                    <p className="text-xs text-muted-foreground mb-3">
                        ID: {pipeline.pipeline_id} · {pipeline.total_agents} agents
                    </p>

                    {/* Stage list with connecting lines */}
                    <div className="space-y-2">
                        {stages.map((stage, i) => (
                            <div key={stage.name}>
                                <StageCard stage={stage} status={stageStatus[stage.name]} />
                                {i < stages.length - 1 && (
                                    <div className="flex justify-center py-1">
                                        <div className="h-3 w-0.5 bg-border" />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </>
            ) : (
                <p className="text-xs text-muted-foreground">
                    No active pipeline. {history.length} completed.
                </p>
            )}
        </div>
    );
}
