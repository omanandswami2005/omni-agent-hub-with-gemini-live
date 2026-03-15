/**
 * VoiceProvider — Global voice session context.
 *
 * Lifts WebSocket, audio capture, audio playback, and video capture out of
 * individual pages so voice + vision interaction persists across all routes.
 *
 * Camera / Screen lifecycle:
 *  - toggleCamera()  → start/stop camera capture, sends JPEG frames to model
 *  - toggleScreen()  → start/stop screen share, sends JPEG frames to model
 *  - Both auto-stop when WS disconnects, browser tab closes, or user clicks
 *    the browser "stop sharing" chrome.
 *  - getPreviewStream()  → returns the live MediaStream for <video> preview
 */

import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useAudioCapture } from '@/hooks/useAudioCapture';
import { useAudioPlayback } from '@/hooks/useAudioPlayback';
import { useVideoCapture } from '@/hooks/useVideoCapture';
import { useKeyboard } from '@/hooks/useKeyboard';
import { useChatStore } from '@/stores/chatStore';
import { useClientStore } from '@/stores/clientStore';
import { getClientType } from '@/lib/constants';
import { toast } from 'sonner';

const VoiceContext = createContext(null);

export function VoiceProvider({ children }) {
    // Single unified WebSocket for both audio and text
    const { sendText, sendAudio, sendImage, sendControl, acquireMic, releaseMic, isConnected, disconnect, reconnect, serverSessionId } = useWebSocket();

    const { startRecording, stopRecording, isRecording, volume: captureVolume, permissionError: micError, clearError: clearMicError, setMuted } = useAudioCapture({
        onAudioData: sendAudio,
    });
    const { stopPlayback, volume: playbackVolume } = useAudioPlayback();

    // Video capture — frames are piped straight to the model via sendImage
    const {
        startCapture,
        stopCapture,
        flipCamera,
        isCapturing: isVideoActive,
        source: videoSource,
        facingMode: _facingMode,
        getPreviewStream,
        permissionError: videoError,
        clearError: clearVideoError,
    } = useVideoCapture({ onFrameData: sendImage });

    const [isMuted, setIsMuted] = useState(false);
    // Voice output toggle — when false, audio blobs are discarded and
    // only text transcriptions are shown.
    const [voiceEnabled, setVoiceEnabled] = useState(true);

    // Derived booleans
    const isScreenSharing = isVideoActive && videoSource === 'screen';
    const isCameraOn = isVideoActive && videoSource === 'camera';

    // Mic floor: auto-stop recording when another device acquires the mic floor
    const micFloorHolder = useClientStore((s) => s.micFloorHolder);
    const myClientType = getClientType();
    // True when another device currently holds the mic floor — block recording start
    const micBlocked = !!(micFloorHolder && micFloorHolder !== myClientType);

    // Wrapper that also sends mic_release to the server when stopping.
    // Use this instead of bare stopRecording() everywhere inside VoiceProvider.
    // IMPORTANT: Must be declared before any useEffect that references it to
    // avoid a TDZ (Temporal Dead Zone) error in production builds.
    const stopRecordingAndRelease = useCallback(() => {
        stopRecording();
        releaseMic();
    }, [stopRecording, releaseMic]);

    // Track previous isConnected to detect disconnects
    const prevConnectedRef = useRef(isConnected);
    useEffect(() => {
        // If connection drops, tear down media to free hardware
        if (prevConnectedRef.current && !isConnected) {
            stopCapture();
            // Stop any ongoing recording when connection drops
            if (isRecording) {
                stopRecordingAndRelease();
            }
            // Stop playback when disconnected
            stopPlayback();
        }
        prevConnectedRef.current = isConnected;
    }, [isConnected, stopCapture, stopRecordingAndRelease, stopPlayback, isRecording]);

    useEffect(() => {
        if (micBlocked && isRecording) {
            stopRecordingAndRelease();
            toast.warning(`Mic in use by ${micFloorHolder}. Stopped recording.`, { duration: 4000 });
        }
    }, [micBlocked, micFloorHolder, isRecording, stopRecordingAndRelease]);

    // ── Toggles ──────────────────────────────────────────────────────

    const toggleRecording = useCallback(() => {
        if (!isConnected && !isRecording) return; // Can't start if live WS disconnected
        if (isRecording) {
            stopRecordingAndRelease();
        } else {
            if (micBlocked) return; // Another device holds the floor — refuse silently
            stopPlayback();
            // Request the mic floor — recording starts only after the server
            // confirms the grant.  This eliminates the race where audio frames
            // are silently dropped during the round-trip to the server.
            acquireMic(() => startRecording());
        }
    }, [isRecording, isConnected, micBlocked, acquireMic, startRecording, stopRecordingAndRelease, stopPlayback]);

    const toggleMute = useCallback(() => {
        const next = !isMuted;
        setIsMuted(next);
        setMuted(next);
    }, [isMuted, setMuted]);

    const toggleVoice = useCallback(() => {
        const next = !voiceEnabled;
        setVoiceEnabled(next);
        // Update chatStore so audio enqueue is skipped when voice is off
        useChatStore.getState().setVoiceOutputEnabled(next);
        // Notify the server (informational — modality switch is frontend-side)
        sendControl('voice_toggle', { voice_enabled: next });
        if (!next) {
            // Disable voice output: stop playback and clear queued audio
            stopPlayback();
            useChatStore.getState().clearAudioQueue?.();
            // Also stop recording if active
            if (isRecording) stopRecordingAndRelease();
        }
    }, [voiceEnabled, sendControl, stopPlayback, isRecording, stopRecordingAndRelease]);

    const toggleScreen = useCallback(async () => {
        if (!isConnected && !isScreenSharing) return; // Can't start if live WS disconnected
        if (isScreenSharing) {
            stopCapture();
            sendControl('screen_share_stop');
        } else {
            // If camera is on, stop it first (mutual exclusion)
            if (isCameraOn) {
                stopCapture();
                sendControl('camera_stop');
            }
            await startCapture('screen');
            sendControl('screen_share_start');
        }
    }, [isConnected, isScreenSharing, isCameraOn, startCapture, stopCapture, sendControl]);

    const toggleCamera = useCallback(async () => {
        if (!isConnected && !isCameraOn) return; // Can't start if live WS disconnected
        if (isCameraOn) {
            stopCapture();
            sendControl('camera_stop');
        } else {
            // If screen is sharing, stop it first
            if (isScreenSharing) {
                stopCapture();
                sendControl('screen_share_stop');
            }
            await startCapture('camera');
            sendControl('camera_start');
        }
    }, [isConnected, isCameraOn, isScreenSharing, startCapture, stopCapture, sendControl]);

    // Stop all media (voice + video) – used by Escape shortcut
    const stopAll = useCallback(() => {
        if (isRecording) stopRecordingAndRelease();
        if (isVideoActive) {
            stopCapture();
            sendControl(isScreenSharing ? 'screen_share_stop' : 'camera_stop');
        }
    }, [isRecording, isVideoActive, isScreenSharing, stopRecordingAndRelease, stopCapture, sendControl]);

    // Global keyboard shortcuts
    useKeyboard({
        escape: stopAll,
    });

    // Combined permission error — mic takes precedence over video for display
    // (only one blocking error shown at a time; clear both on dismiss)
    const permissionError = micError || videoError;
    const clearPermissionError = useCallback(() => {
        clearMicError();
        clearVideoError();
    }, [clearMicError, clearVideoError]);

    const value = useMemo(
        () => ({
            // WebSocket
            sendText,
            sendAudio,
            sendImage,
            sendControl,
            isConnected,
            disconnect,
            reconnect,
            serverSessionId,
            // Audio state
            isRecording,
            isMuted,
            voiceEnabled,
            captureVolume,
            playbackVolume,
            micBlocked,
            // Video state
            isScreenSharing,
            isCameraOn,
            isVideoActive,
            videoSource,
            getPreviewStream,
            // Permission errors
            permissionError,
            clearPermissionError,
            // Actions
            toggleRecording,
            toggleMute,
            toggleVoice,
            toggleScreen,
            toggleCamera,
            flipCamera,
            stopPlayback,
            stopCapture,
            stopAll,
        }),
        [
            sendText, sendAudio, sendImage, sendControl, isConnected, disconnect,
            reconnect, serverSessionId,
            isRecording, isMuted, voiceEnabled, captureVolume, playbackVolume, micBlocked,
            isScreenSharing, isCameraOn, isVideoActive, videoSource, getPreviewStream,
            permissionError, clearPermissionError,
            toggleRecording, toggleMute, toggleVoice, toggleScreen, toggleCamera,
            flipCamera, stopPlayback, stopCapture, stopAll,
        ],
    );

    return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}

export function useVoice() {
    const ctx = useContext(VoiceContext);
    if (!ctx) throw new Error('useVoice must be used within <VoiceProvider>');
    return ctx;
}
