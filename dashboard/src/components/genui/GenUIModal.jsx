/**
 * GenUI: GenUIModal — Expand any GenUI block into a full-screen modal overlay.
 * Wrap around GenUIRenderer inline content and show an expand button.
 */

import { useState, useCallback } from 'react';
import { X, Maximize2 } from 'lucide-react';
import { cn } from '@/lib/cn';
import GenUIRenderer from '@/components/genui/GenUIRenderer';

export default function GenUIModal({ type, data, className }) {
    const [open, setOpen] = useState(false);

    const handleClose = useCallback(() => setOpen(false), []);

    return (
        <>
            {/* Inline preview with expand button */}
            <div className={cn('group relative', className)}>
                <GenUIRenderer type={type} data={data} />
                <button
                    onClick={() => setOpen(true)}
                    className="absolute top-2 right-2 flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.08] bg-card/90 backdrop-blur-sm text-muted-foreground opacity-0 transition-all hover:bg-white/[0.08] hover:text-foreground group-hover:opacity-100"
                    title="Expand"
                >
                    <Maximize2 size={13} />
                </button>
            </div>

            {/* Full-screen modal */}
            {open && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
                    onClick={handleClose}
                >
                    <div
                        className="relative flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-card shadow-2xl"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
                            <h3 className="text-sm font-semibold text-foreground">Generated UI — {type}</h3>
                            <button
                                onClick={handleClose}
                                className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-white/[0.06] text-muted-foreground transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>
                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-6">
                            <GenUIRenderer type={type} data={data} />
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
