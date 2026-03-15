/**
 * Sandbox: DesktopViewer — Embedded cloud desktop viewer.
 *
 * Displays the E2B desktop stream in an iframe. Shows desktop status,
 * start/stop controls, and the live stream when available.
 */

import { useState, useCallback, useRef } from 'react';
import { useTaskStore } from '@/stores/taskStore';
import { api } from '@/lib/api';
import { Monitor, Play, Square, RefreshCw, Maximize2, Minimize2, Upload, CheckCircle } from 'lucide-react';

export default function DesktopViewer() {
    const desktop = useTaskStore((s) => s.desktop);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [expanded, setExpanded] = useState(false);
    const [uploadStatus, setUploadStatus] = useState(null); // null | 'uploading' | {name, path}
    const fileInputRef = useRef(null);

    const startDesktop = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.post('/tasks/desktop/start');
            useTaskStore.getState().setDesktop(res);
        } catch (err) {
            setError(err?.message || 'Failed to start desktop');
        } finally {
            setLoading(false);
        }
    }, []);

    const stopDesktop = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            await api.post('/tasks/desktop/stop');
            useTaskStore.getState().setDesktop(null);
        } catch (err) {
            setError(err?.message || 'Failed to stop desktop');
        } finally {
            setLoading(false);
        }
    }, []);

    const handleFileUpload = useCallback(async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setUploadStatus('uploading');
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('path', '/home/user');
            await api.postForm('/tasks/desktop/upload', formData);
            setUploadStatus({ name: file.name, path: `/home/user/${file.name}` });
            setTimeout(() => setUploadStatus(null), 4000);
        } catch (err) {
            setError(err?.message || 'Upload failed');
            setUploadStatus(null);
        } finally {
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    }, []);

    // Backend E2B service returns statuses: creating, ready, streaming, working, idle, destroyed, error
    const isRunning = !!desktop?.status && !['destroyed', 'error', 'none'].includes(desktop.status);
    const streamUrl = desktop?.stream_url;

    // No desktop state yet — show start button
    if (!desktop) {
        return (
            <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border p-12">
                <Monitor size={40} className="text-muted-foreground" />
                <div className="text-center">
                    <h3 className="font-medium">Cloud Desktop</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Start a cloud desktop to run apps, browse the web, and execute code in a sandboxed environment.
                    </p>
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <button
                    onClick={startDesktop}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                    {loading ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                    {loading ? 'Starting…' : 'Start Desktop'}
                </button>
            </div>
        );
    }

    return (
        <div className={`flex flex-col gap-3 ${expanded ? 'fixed inset-0 z-50 bg-background p-4' : ''}`}>
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Monitor size={16} className="text-primary" />
                    <span className="text-sm font-medium">Cloud Desktop</span>
                    <span className={`flex h-2 w-2 rounded-full ${isRunning ? 'bg-green-500' : 'bg-yellow-500'}`} />
                    <span className="text-xs text-muted-foreground">{desktop.status}</span>
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={() => setExpanded((e) => !e)}
                        className="rounded p-1 hover:bg-muted"
                        aria-label={expanded ? 'Collapse' : 'Expand'}
                    >
                        {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    </button>
                    {isRunning && (
                        <button
                            onClick={stopDesktop}
                            disabled={loading}
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
                        >
                            <Square size={12} />
                            Stop
                        </button>
                    )}
                </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            {/* Desktop stream iframe */}
            {isRunning && streamUrl ? (
                <div className={`overflow-hidden rounded-lg border border-border bg-black ${expanded ? 'flex-1' : 'aspect-video'}`}>
                    <iframe
                        src={streamUrl}
                        title="Cloud Desktop"
                        className="h-full w-full"
                        sandbox="allow-scripts allow-same-origin"
                        allow="clipboard-read; clipboard-write"
                    />
                </div>
            ) : (
                <div className="flex aspect-video items-center justify-center rounded-lg border border-border bg-muted/30">
                    <div className="text-center text-sm text-muted-foreground">
                        {isRunning ? 'Stream URL not available' : 'Desktop is not running'}
                        {!isRunning && (
                            <button
                                onClick={startDesktop}
                                disabled={loading}
                                className="mt-2 flex items-center gap-1 mx-auto rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                            >
                                {loading ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
                                Restart
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* File upload */}
            {isRunning && (
                <div className="flex items-center gap-2">
                    <input
                        ref={fileInputRef}
                        type="file"
                        onChange={handleFileUpload}
                        className="hidden"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploadStatus === 'uploading'}
                        className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
                    >
                        {uploadStatus === 'uploading' ? (
                            <RefreshCw size={12} className="animate-spin" />
                        ) : (
                            <Upload size={12} />
                        )}
                        {uploadStatus === 'uploading' ? 'Uploading…' : 'Upload File'}
                    </button>
                    {uploadStatus && uploadStatus !== 'uploading' && (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                            <CheckCircle size={12} />
                            {uploadStatus.name} → {uploadStatus.path}
                        </span>
                    )}
                </div>
            )}

            {/* Desktop info */}
            {desktop.sandbox_id && (
                <p className="text-[10px] text-muted-foreground">
                    Sandbox: {desktop.sandbox_id}
                </p>
            )}
        </div>
    );
}
