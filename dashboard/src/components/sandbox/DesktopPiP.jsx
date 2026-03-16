/**
 * DesktopPiP — Draggable Picture-in-Picture desktop preview overlay.
 *
 * Floats above all content, allowing users to see the E2B desktop stream
 * while working on other tabs. Draggable, resizable (small/medium), and
 * dismissible. Only renders when a desktop is running and the user isn't
 * already on the Desktop tab.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useTaskStore } from '@/stores/taskStore';
import { Monitor, X, Minimize2, Maximize2, GripHorizontal, Eye } from 'lucide-react';

const SIZES = {
    small: { width: 280, height: 180 },
    medium: { width: 420, height: 270 },
};

export default function DesktopPiP({ visible = true }) {
    const desktop = useTaskStore((s) => s.desktop);
    const isAgentStreaming = useTaskStore((s) => s.isAgentStreaming);

    const [dismissed, setDismissed] = useState(false);
    const [size, setSize] = useState('small');
    const [position, setPosition] = useState({ x: 16, y: 16 }); // bottom-right offset
    const dragRef = useRef(null);
    const isDragging = useRef(false);
    const dragOffset = useRef({ x: 0, y: 0 });

    const isRunning = !!desktop?.status && !['destroyed', 'error', 'none'].includes(desktop.status);
    const streamUrl = desktop?.stream_url;

    // Reset dismissed state when desktop starts/stops
    useEffect(() => {
        if (isRunning) setDismissed(false);
    }, [isRunning]);

    const handleMouseDown = useCallback((e) => {
        if (e.target.closest('[data-no-drag]')) return;
        isDragging.current = true;
        const rect = dragRef.current.getBoundingClientRect();
        dragOffset.current = {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
        };
        e.preventDefault();
    }, []);

    useEffect(() => {
        const handleMouseMove = (e) => {
            if (!isDragging.current) return;
            const newX = e.clientX - dragOffset.current.x;
            const newY = e.clientY - dragOffset.current.y;
            // Clamp within viewport
            const maxX = window.innerWidth - (SIZES[size]?.width || 280) - 8;
            const maxY = window.innerHeight - (SIZES[size]?.height || 180) - 8;
            setPosition({
                x: Math.max(8, Math.min(newX, maxX)),
                y: Math.max(8, Math.min(newY, maxY)),
            });
        };
        const handleMouseUp = () => {
            isDragging.current = false;
        };
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [size]);

    // Don't render if no running desktop, dismissed, or not visible
    if (!isRunning || !streamUrl || dismissed || !visible) return null;

    const { width, height } = SIZES[size];

    return (
        <div
            ref={dragRef}
            onMouseDown={handleMouseDown}
            className="fixed z-[60] overflow-hidden rounded-2xl border border-white/[0.12] bg-black/90 shadow-2xl backdrop-blur-sm"
            style={{
                width: `${width}px`,
                height: `${height + 32}px`, // +32 for header
                left: `${position.x}px`,
                top: `${position.y}px`,
                cursor: isDragging.current ? 'grabbing' : 'grab',
            }}
        >
            {/* Header bar */}
            <div className="flex h-8 items-center justify-between bg-white/[0.06] px-2">
                <div className="flex items-center gap-1.5">
                    <GripHorizontal size={12} className="text-muted-foreground" />
                    <Monitor size={11} className="text-foreground/60" />
                    <span className="text-[10px] font-medium text-foreground/70">Desktop</span>
                    {isAgentStreaming && (
                        <span className="flex items-center gap-0.5 text-[9px] text-blue-400">
                            <Eye size={9} />
                            Live
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-0.5" data-no-drag>
                    <button
                        onClick={() => setSize(size === 'small' ? 'medium' : 'small')}
                        className="rounded p-1 hover:bg-white/[0.08] transition-colors"
                        title={size === 'small' ? 'Enlarge' : 'Shrink'}
                    >
                        {size === 'small' ? <Maximize2 size={10} /> : <Minimize2 size={10} />}
                    </button>
                    <button
                        onClick={() => setDismissed(true)}
                        className="rounded p-1 hover:bg-white/[0.08] transition-colors"
                        title="Dismiss preview"
                    >
                        <X size={10} />
                    </button>
                </div>
            </div>

            {/* Stream iframe */}
            <iframe
                src={streamUrl}
                title="Desktop Preview"
                className="h-full w-full"
                style={{ height: `${height}px`, pointerEvents: 'none' }}
                sandbox="allow-scripts allow-same-origin"
                tabIndex={-1}
            />
        </div>
    );
}
