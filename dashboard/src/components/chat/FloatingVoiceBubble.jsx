/**
 * FloatingVoiceBubble — Global persistent voice control overlay.
 *
 * Always visible as a floating orb at the bottom-right corner.
 * On hover/click expands to reveal controls: mute, start/stop, screen share, camera.
 * Works across ALL pages — even Settings, Sessions, etc.
 *
 * When camera or screen share is active, shows a small live-feed badge on the orb
 * and the controls reflect the active media state.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '@/lib/cn';
import { useChatStore } from '@/stores/chatStore';
import {
    Mic,
    MicOff,
    Phone,
    PhoneOff,
    Monitor,
    MonitorOff,
    Camera,
    CameraOff,
    MessageSquare,
    Video,
} from 'lucide-react';

const ORB_COLORS = {
    idle: 'from-blue-500/80 to-indigo-600/80',
    listening: 'from-red-500 to-rose-600',
    processing: 'from-amber-500 to-orange-500',
    thinking: 'from-amber-500 to-orange-500',
    speaking: 'from-emerald-500 to-green-600',
    error: 'from-red-700 to-red-800',
};

const PULSE_CLASSES = {
    idle: '',
    listening: 'animate-[pulse_1.4s_ease-in-out_infinite]',
    processing: 'animate-spin',
    thinking: 'animate-spin',
    speaking: 'animate-[pulse_2s_ease-in-out_infinite]',
    error: '',
};

export default function FloatingVoiceBubble({
    isRecording,
    isMuted,
    isScreenSharing,
    isCameraOn,
    isVideoActive,
    captureVolume = 0,
    playbackVolume = 0,
    onToggleRecording,
    onToggleMute,
    onToggleScreen,
    onToggleCamera,
    onOpenChat,
    isConnected,
}) {
    const agentState = useChatStore((s) => s.agentState);
    const [isExpanded, setIsExpanded] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const hoverTimeout = useRef(null);
    const containerRef = useRef(null);

    const state = isRecording ? 'listening' : agentState;
    const volume = state === 'listening' ? captureVolume : state === 'speaking' ? playbackVolume : 0;

    // Auto-collapse after 3s of no hover
    const startCollapseTimer = useCallback(() => {
        clearTimeout(hoverTimeout.current);
        hoverTimeout.current = setTimeout(() => setIsExpanded(false), 3000);
    }, []);

    const handleMouseEnter = () => {
        clearTimeout(hoverTimeout.current);
        setIsExpanded(true);
    };

    const handleMouseLeave = () => {
        startCollapseTimer();
    };

    useEffect(() => {
        return () => clearTimeout(hoverTimeout.current);
    }, []);

    // Ring scale based on audio volume
    const ringScale = 1 + volume * 0.5;

    const controls = [
        {
            icon: isMuted ? MicOff : Mic,
            label: isMuted ? 'Unmute' : 'Mute',
            onClick: onToggleMute,
            active: !isMuted,
            color: isMuted ? 'text-red-400' : 'text-emerald-400',
        },
        {
            icon: isRecording ? PhoneOff : Phone,
            label: isRecording ? 'Stop' : 'Start',
            onClick: onToggleRecording,
            active: isRecording,
            color: isRecording ? 'text-red-400' : 'text-emerald-400',
        },
        {
            icon: isScreenSharing ? MonitorOff : Monitor,
            label: isScreenSharing ? 'Stop Share' : 'Share Screen',
            onClick: onToggleScreen,
            active: isScreenSharing,
            color: isScreenSharing ? 'text-blue-400' : 'text-muted-foreground',
        },
        {
            icon: isCameraOn ? CameraOff : Camera,
            label: isCameraOn ? 'Camera Off' : 'Camera On',
            onClick: onToggleCamera,
            active: isCameraOn,
            color: isCameraOn ? 'text-blue-400' : 'text-muted-foreground',
        },
    ];

    return (
        <div
            ref={containerRef}
            className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3"
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
        >
            {/* Expanded controls panel */}
            <div
                className={cn(
                    'flex flex-col items-center gap-2 transition-all duration-300 ease-out',
                    isExpanded
                        ? 'pointer-events-auto translate-y-0 opacity-100'
                        : 'pointer-events-none translate-y-4 opacity-0',
                )}
            >
                {/* Chat shortcut */}
                <ControlButton
                    icon={MessageSquare}
                    label="Chat"
                    onClick={onOpenChat}
                    color="text-primary"
                    active={false}
                />

                {/* Divider */}
                <div className="h-px w-8 bg-border/50" />

                {/* Control buttons */}
                {controls.map((ctrl) => (
                    <ControlButton key={ctrl.label} {...ctrl} />
                ))}
            </div>

            {/* Main orb */}
            <button
                onClick={onToggleRecording}
                className={cn(
                    'group relative flex h-14 w-14 items-center justify-center rounded-full shadow-2xl',
                    'bg-gradient-to-br transition-all duration-300',
                    'hover:scale-110 active:scale-95',
                    'ring-2 ring-white/10 backdrop-blur-xl',
                    ORB_COLORS[state] || ORB_COLORS.idle,
                    PULSE_CLASSES[state],
                )}
                aria-label={`Voice — ${state}`}
            >
                {/* Volume ring */}
                <div
                    className={cn(
                        'absolute inset-0 rounded-full transition-transform duration-100',
                        state === 'listening' && 'bg-red-500/20',
                        state === 'speaking' && 'bg-emerald-500/20',
                    )}
                    style={{
                        transform: `scale(${ringScale})`,
                        opacity: volume > 0.02 ? 0.7 : 0,
                    }}
                />

                {/* Connection dot */}
                <div
                    className={cn(
                        'absolute right-0 top-0 h-3 w-3 rounded-full border-2 border-background',
                        isConnected ? 'bg-emerald-400' : 'bg-red-400',
                    )}
                />

                {/* Video active badge */}
                {isVideoActive && (
                    <div className="absolute -left-1 top-0 flex h-4 w-4 items-center justify-center rounded-full border-2 border-background bg-blue-500">
                        <Video size={8} className="text-white" />
                    </div>
                )}

                {/* Icon */}
                <div className="relative z-10">
                    {isRecording ? (
                        <Mic size={20} className="text-white" />
                    ) : state === 'speaking' ? (
                        <div className="flex items-center gap-0.5">
                            {[1, 2, 3].map((i) => (
                                <div
                                    key={i}
                                    className="w-0.5 rounded-full bg-white animate-[soundbar_0.6s_ease-in-out_infinite]"
                                    style={{
                                        height: `${8 + Math.random() * 10}px`,
                                        animationDelay: `${i * 0.15}s`,
                                    }}
                                />
                            ))}
                        </div>
                    ) : state === 'processing' || state === 'thinking' ? (
                        <div className="h-5 w-5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    ) : (
                        <Mic size={20} className="text-white/90" />
                    )}
                </div>
            </button>
        </div>
    );
}

function ControlButton({ icon: Icon, label, onClick, active, color }) {
    return (
        <div className="group/btn relative">
            <button
                onClick={onClick}
                className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-full',
                    'border border-border/60 bg-background/90 backdrop-blur-xl shadow-lg',
                    'transition-all duration-200 hover:scale-110 active:scale-95',
                    active && 'ring-2 ring-primary/30',
                )}
                aria-label={label}
            >
                <Icon size={16} className={cn(color)} />
            </button>
            {/* Tooltip */}
            <span className="pointer-events-none absolute right-full mr-3 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-md bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md opacity-0 transition-opacity group-hover/btn:opacity-100">
                {label}
            </span>
        </div>
    );
}
