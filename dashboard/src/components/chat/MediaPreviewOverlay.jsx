/**
 * MediaPreviewOverlay — Picture-in-picture style floating preview
 * for the active camera or screen-share stream.
 *
 * Sits just above the FloatingVoiceBubble (bottom-right) so it doesn't
 * obstruct the main content.  Draggable future-proofed via CSS classes.
 */

import { useRef, useEffect, useState } from 'react';
import { cn } from '@/lib/cn';
import { Camera, Monitor, X, Maximize2, Minimize2 } from 'lucide-react';

export default function MediaPreviewOverlay({ stream, source, onClose }) {
    const videoRef = useRef(null);
    const [isMinimised, setIsMinimised] = useState(false);

    // Attach the live MediaStream to the <video> element
    useEffect(() => {
        const el = videoRef.current;
        if (!el || !stream) return;
        el.srcObject = stream;
        el.play().catch(() => { });
        return () => { el.srcObject = null; };
    }, [stream]);

    if (!stream) return null;

    const SourceIcon = source === 'screen' ? Monitor : Camera;
    const label = source === 'screen' ? 'Screen Share' : 'Camera';

    return (
        <div
            className={cn(
                'fixed z-50 transition-all duration-300 ease-out',
                // Position just above the voice bubble
                'bottom-24 right-6',
                isMinimised ? 'h-10 w-40' : 'h-40 w-64 sm:h-48 sm:w-80',
            )}
        >
            <div
                className={cn(
                    'relative h-full w-full overflow-hidden rounded-xl border border-border/60',
                    'bg-black shadow-2xl ring-1 ring-white/5',
                )}
            >
                {/* Video feed */}
                <video
                    ref={videoRef}
                    muted
                    playsInline
                    className={cn(
                        'h-full w-full object-cover transition-opacity duration-200',
                        isMinimised && 'opacity-0',
                    )}
                />

                {/* Header bar */}
                <div className="absolute inset-x-0 top-0 flex items-center justify-between bg-gradient-to-b from-black/70 to-transparent px-3 py-2">
                    <div className="flex items-center gap-1.5 text-xs text-white/80">
                        <SourceIcon size={12} />
                        <span>{label}</span>
                        {/* Live dot */}
                        <span className="ml-1 flex h-2 w-2">
                            <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-red-400 opacity-75" />
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
                        </span>
                    </div>

                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setIsMinimised((m) => !m)}
                            className="rounded p-0.5 hover:bg-white/20"
                            aria-label={isMinimised ? 'Maximise preview' : 'Minimise preview'}
                        >
                            {isMinimised ? <Maximize2 size={12} className="text-white/80" /> : <Minimize2 size={12} className="text-white/80" />}
                        </button>
                        <button
                            onClick={onClose}
                            className="rounded p-0.5 hover:bg-white/20"
                            aria-label="Stop sharing"
                        >
                            <X size={12} className="text-white/80" />
                        </button>
                    </div>
                </div>

                {/* Minimised label */}
                {isMinimised && (
                    <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs text-white/70">
                        <SourceIcon size={14} />
                        <span>{label} active</span>
                    </div>
                )}
            </div>
        </div>
    );
}
