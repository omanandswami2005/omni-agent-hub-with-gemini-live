import { create } from 'zustand';

/**
 * Task Store — Tracks PlannedTask lifecycle, steps, and human-in-the-loop inputs.
 *
 * Receives events from /ws/events channel:
 *   - task_created       → new task added
 *   - task_planned       → task decomposed into steps
 *   - task_updated       → task status changed
 *   - task_step_update   → individual step progress
 *   - task_completed     → task finished
 *   - task_input_required → agent needs user input
 *   - e2b_desktop_status → desktop sandbox status change
 */
export const useTaskStore = create((set, get) => ({
    // All tasks: { [taskId]: taskObject }
    tasks: {},
    // Active task ID being viewed
    activeTaskId: null,
    // Pending human input requests: { [inputId]: inputObject }
    pendingInputs: {},
    // E2B Desktop status
    desktop: null,
    // Agent vision streaming active
    isAgentStreaming: false,
    // Task panel open
    isPanelOpen: false,

    // ── Actions ──

    /** Set a task (from task_created, task_planned, task_updated events) */
    setTask: (task) => {
        set((state) => ({
            tasks: { ...state.tasks, [task.id]: task },
        }));
    },

    /** Update a specific step in a task */
    updateStep: (taskId, step) => {
        set((state) => {
            const task = state.tasks[taskId];
            if (!task) return state;
            const steps = (task.steps || []).map((s) =>
                s.id === step.id ? { ...s, ...step } : s
            );
            return {
                tasks: {
                    ...state.tasks,
                    [taskId]: { ...task, steps, progress: step.progress ?? task.progress },
                },
            };
        });
    },

    /** Add a pending input request */
    addPendingInput: (input) => {
        set((state) => ({
            pendingInputs: { ...state.pendingInputs, [input.id]: input },
        }));
    },

    /** Remove a pending input (after response) */
    removePendingInput: (inputId) => {
        set((state) => {
            const { [inputId]: _, ...rest } = state.pendingInputs;
            return { pendingInputs: rest };
        });
    },

    /** Set active task for detail view */
    setActiveTask: (taskId) => set({ activeTaskId: taskId, isPanelOpen: true }),

    /** Toggle task panel */
    togglePanel: () => set((state) => ({ isPanelOpen: !state.isPanelOpen })),
    openPanel: () => set({ isPanelOpen: true }),
    closePanel: () => set({ isPanelOpen: false }),

    /** Update desktop status */
    setDesktop: (desktop) => set({ desktop }),

    /** Update agent streaming state */
    setAgentStreaming: (isAgentStreaming) => set({ isAgentStreaming }),

    /** Remove a task */
    removeTask: (taskId) => {
        set((state) => {
            const { [taskId]: _, ...rest } = state.tasks;
            return {
                tasks: rest,
                activeTaskId: state.activeTaskId === taskId ? null : state.activeTaskId,
            };
        });
    },

    /** Clear all tasks */
    clearTasks: () => set({ tasks: {}, activeTaskId: null, pendingInputs: {} }),

    /** Route an event from /ws/events channel */
    handleEvent: (event) => {
        const { setTask, updateStep, addPendingInput, setDesktop } = get();
        switch (event.type) {
            case 'task_created':
            case 'task_planned':
            case 'task_updated':
            case 'task_completed':
                if (event.task) {
                    setTask(event.task);
                }
                break;

            case 'task_step_update':
                if (event.task_id && event.step) {
                    updateStep(event.task_id, { ...event.step, progress: event.progress });
                }
                break;

            case 'task_input_required':
                if (event.input) {
                    addPendingInput({
                        ...event.input,
                        taskId: event.task_id,
                    });
                }
                break;

            case 'e2b_desktop_status':
                if (event.desktop) {
                    setDesktop(event.desktop);
                }
                break;

            default:
                break;
        }
    },

    // ── Selectors ──

    /** Get sorted task list (newest first) */
    getTaskList: () => {
        const tasks = Object.values(get().tasks);
        return tasks.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    },

    /** Get active task */
    getActiveTask: () => {
        const { tasks, activeTaskId } = get();
        return activeTaskId ? tasks[activeTaskId] : null;
    },

    /** Get pending inputs for a specific task */
    getInputsForTask: (taskId) => {
        return Object.values(get().pendingInputs).filter((i) => i.taskId === taskId);
    },

    /** Check if any task is running */
    hasRunningTask: () => {
        return Object.values(get().tasks).some((t) => t.status === 'running');
    },
}));
