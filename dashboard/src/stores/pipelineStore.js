import { create } from 'zustand';

/**
 * Pipeline Store — Tracks TaskArchitect pipeline decomposition & execution.
 *
 * Receives events from the /ws/events channel:
 *   - pipeline_created  → full blueprint with stages
 *   - pipeline_progress → per-stage status updates
 */
export const usePipelineStore = create((set, get) => ({
    // Current active pipeline (null when idle)
    pipeline: null,
    // { [stageName]: { status, progress } }
    stageStatus: {},
    // History of completed pipelines (keep last 5)
    history: [],

    // ── Actions ──

    /** Called on pipeline_created event */
    setPipeline: (blueprint) => {
        const initial = {};
        for (const stage of blueprint.stages || []) {
            initial[stage.name] = { status: 'pending', progress: 0 };
        }
        set({ pipeline: blueprint, stageStatus: initial });
    },

    /** Called on pipeline_progress event */
    updateStage: (stageName, status, progress = 0) => {
        set((state) => ({
            stageStatus: {
                ...state.stageStatus,
                [stageName]: { status, progress },
            },
        }));

        // If all stages are completed or failed, archive the pipeline
        const { pipeline } = get();
        if (!pipeline) return;
        const stages = pipeline.stages || [];
        const updatedStatus = get().stageStatus;
        const reallyDone = stages.every((s) => {
            const st = updatedStatus[s.name];
            return st && (st.status === 'completed' || st.status === 'failed');
        });
        if (reallyDone) {
            set((state) => ({
                history: [
                    { ...state.pipeline, stageStatus: { ...state.stageStatus }, completedAt: new Date().toISOString() },
                    ...state.history,
                ].slice(0, 5),
            }));
        }
    },

    /** Clear active pipeline */
    clearPipeline: () => set({ pipeline: null, stageStatus: {} }),

    /** Route an event from the /ws/events channel */
    handleEvent: (event) => {
        const { setPipeline, updateStage } = get();
        switch (event.type) {
            case 'pipeline_created':
                setPipeline(event.pipeline);
                break;
            case 'pipeline_progress':
                updateStage(event.stage, event.status, event.progress);
                break;
            default:
                break;
        }
    },
}));
