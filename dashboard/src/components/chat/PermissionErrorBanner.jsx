/**
 * PermissionErrorBanner — Floating toast shown when the user has blocked
 * mic / camera / screen-share permissions and tries to use them again.
 *
 * Anchored bottom-right, just above the FloatingVoiceBubble.
 * Auto-dismisses after 8 s; has a manual X button.
 * Shows browser-specific guidance on how to re-enable access.
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/cn';
import { AlertTriangle, X, MicOff, CameraOff, Monitor, Lock, WifiOff, HelpCircle } from 'lucide-react';

const AUTO_DISMISS_MS = 8000;

const ICON_MAP = {
    microphone: MicOff,
    camera: CameraOff,
    screen: Monitor,
};

const TYPE_STYLES = {
    denied: { bar: 'bg-red-500', icon: Lock, badge: 'bg-red-500/15 text-red-400 border-red-500/30' },
    not_found: { bar: 'bg-amber-500', icon: AlertTriangle, badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
    busy: { bar: 'bg-amber-500', icon: AlertTriangle, badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
    security: { bar: 'bg-purple-500', icon: Lock, badge: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
    unknown: { bar: 'bg-zinc-500', icon: HelpCircle, badge: 'bg-zinc-500/15 text-muted-foreground border-border' },
};

export default function PermissionErrorBanner({ error, onDismiss }) {
    const timerRef = useRef(null);

    // Auto-dismiss
    useEffect(() => {
        if (!error) return;
        clearTimeout(timerRef.current);
        timerRef.current = setTimeout(onDismiss, AUTO_DISMISS_MS);
        return () => clearTimeout(timerRef.current);
    }, [error, onDismiss]);

    if (!error) return null;

    const styles = TYPE_STYLES[error.type] || TYPE_STYLES.unknown;
    const DeviceIcon = ICON_MAP[error.device] || AlertTriangle;
    const TypeIcon = styles.icon;

    return (
        <div
            role="alert"
            aria-live="assertive"
            className={cn(
                'fixed z-50 w-80 overflow-hidden rounded-xl shadow-2xl',
                // Sits above the voice bubble (bottom-24) and below the preview (bottom-64)
                'bottom-[5.5rem] right-6',
                'border bg-background/95 backdrop-blur-xl',
                styles.badge,
                // Slide-in animation
                'animate-in slide-in-from-right-5 duration-300',
            )}
        >
            {/* Left accent bar */}
            <div className={cn('absolute inset-y-0 left-0 w-1', styles.bar)} />

            {/* Progress bar (shrinks over AUTO_DISMISS_MS) */}
            <div className={cn('absolute bottom-0 left-0 right-0 h-0.5 origin-left', styles.bar)}
                style={{ animation: `shrink-x ${AUTO_DISMISS_MS}ms linear forwards` }}
            />

            <div className="pl-4 pr-3 py-3">
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <DeviceIcon size={15} className="mt-0.5 shrink-0" />
                        <TypeIcon size={13} className="mt-0.5 shrink-0 opacity-70" />
                        <p className="text-sm font-semibold leading-tight">{error.title}</p>
                    </div>
                    <button
                        onClick={onDismiss}
                        className="mt-0.5 shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
                        aria-label="Dismiss"
                    >
                        <X size={14} />
                    </button>
                </div>

                {/* Body */}
                <p className="mt-1.5 pl-8 text-xs leading-relaxed opacity-80">
                    {error.message}
                </p>

                {/* "How to fix" nudge for denied errors */}
                {error.type === 'denied' && (
                    <div className="mt-2 pl-8">
                        <BrowserHint device={error.device} />
                    </div>
                )}
            </div>
        </div>
    );
}

/**
 * Detects the current browser and shows the relevant icon-by-icon steps
 * to re-enable permission in the address bar.
 */
function BrowserHint({ device }) {
    const isChrome = navigator.userAgent.includes('Chrome') && !navigator.userAgent.includes('Edg');
    const isFirefox = navigator.userAgent.includes('Firefox');
    const isSafari = navigator.userAgent.includes('Safari') && !navigator.userAgent.includes('Chrome');
    const isEdge = navigator.userAgent.includes('Edg/');

    let steps;
    if (isFirefox) {
        steps = [
            'Click the 🔒 icon in the address bar',
            `Set ${device === 'microphone' ? 'Microphone' : 'Camera'} → Allow`,
            'Reload the page',
        ];
    } else if (isSafari) {
        steps = [
            'Safari → Settings for this Website',
            `Set ${device === 'microphone' ? 'Microphone' : 'Camera'} → Allow`,
        ];
    } else if (isEdge) {
        steps = [
            'Click 🔒 in the address bar',
            `${device === 'microphone' ? 'Microphone' : 'Camera'} → Allow`,
        ];
    } else {
        // Chrome (default)
        steps = [
            'Click 🔒 in the address bar',
            `Set ${device === 'microphone' ? 'Microphone' : 'Camera'} → Allow`,
        ];
    }

    return (
        <ol className="space-y-0.5 text-xs opacity-70">
            {steps.map((step, i) => (
                <li key={i} className="flex gap-1.5">
                    <span className="shrink-0 font-mono">{i + 1}.</span>
                    <span>{step}</span>
                </li>
            ))}
        </ol>
    );
}
