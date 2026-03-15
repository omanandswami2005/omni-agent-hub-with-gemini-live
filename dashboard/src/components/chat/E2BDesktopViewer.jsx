/**
 * E2BDesktopViewer — Displays the E2B Desktop sandbox stream.
 *
 * Shows desktop status, embedded stream iframe, and start/stop controls.
 * Desktop state comes from taskStore.desktop (populated via e2b_desktop_status events).
 */

import { useState, useCallback } from 'react';
import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { Monitor, Power, PowerOff, Loader2, AlertCircle } from 'lucide-react';

const STATUS_LABELS = {
    creating: 'Starting desktop...',
    ready: 'Desktop ready',
    streaming: 'Desktop streaming',
    working: 'Agent working...',
    idle: 'Desktop idle',
    destroyed: 'Desktop stopped',
    error: 'Desktop error',
};

export default function E2BDesktopViewer() {
    const desktop = useTaskStore((s) => s.desktop);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleStart = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.post('/tasks/desktop/start');
            if (res.desktop) {
                useTaskStore.getState().setDesktop(res.desktop);
            }
        } catch (err) {
            setError(err.message || 'Failed to start desktop');
        } finally {
            setLoading(false);
        }
    }, []);

    const handleStop = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            await api.post('/tasks/desktop/stop');
            useTaskStore.getState().setDesktop(null);
        } catch (err) {
            setError(err.message || 'Failed to stop desktop');
        } finally {
            setLoading(false);
        }
    }, []);

    const isActive = desktop && !['destroyed', 'error'].includes(desktop.status);
    const streamUrl = desktop?.stream_url;

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b border-border">
                <div className="flex items-center gap-2">
                    <Monitor className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Desktop</span>
                    {desktop && (
                        <span className={cn(
                            'text-xs px-1.5 py-0.5 rounded-full',
                            isActive
                                ? 'bg-green-100 text-green-700 dark:bg-green-500/10 dark:text-green-400'
                                : 'bg-muted text-muted-foreground'
                        )}>
                            {STATUS_LABELS[desktop.status] || desktop.status}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-1">
                    {!isActive ? (
                        <button
                            onClick={handleStart}
                            disabled={loading}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                        >
                            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Power className="h-3 w-3" />}
                            Start
                        </button>
                    ) : (
                        <button
                            onClick={handleStop}
                            disabled={loading}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-red-500/10 text-red-500 hover:bg-red-500/20 disabled:opacity-50"
                        >
                            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <PowerOff className="h-3 w-3" />}
                            Stop
                        </button>
                    )}
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 p-2 mx-3 mt-2 rounded-md bg-red-50 dark:bg-red-500/10 text-red-500 text-xs">
                    <AlertCircle className="h-3 w-3 flex-shrink-0" />
                    {error}
                </div>
            )}

            {/* Stream / Placeholder */}
            <div className="flex-1 min-h-0">
                {isActive && streamUrl ? (
                    <iframe
                        src={streamUrl}
                        title="E2B Desktop"
                        className="w-full h-full border-0"
                        sandbox="allow-scripts allow-same-origin"
                    />
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3 p-6">
                        <Monitor className="h-12 w-12 opacity-30" />
                        <p className="text-sm text-center">
                            {desktop?.status === 'creating'
                                ? 'Starting desktop sandbox...'
                                : 'Start a desktop to see the agent work visually'}
                        </p>
                        {desktop?.status === 'creating' && (
                            <Loader2 className="h-5 w-5 animate-spin" />
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
