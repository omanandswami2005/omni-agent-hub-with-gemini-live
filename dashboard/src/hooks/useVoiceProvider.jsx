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
import { useChatWebSocket } from '@/hooks/useChatWebSocket';
import { useAudioCapture } from '@/hooks/useAudioCapture';
import { useAudioPlayback } from '@/hooks/useAudioPlayback';
import { useVideoCapture } from '@/hooks/useVideoCapture';
import { useKeyboard } from '@/hooks/useKeyboard';

const VoiceContext = createContext(null);

export function VoiceProvider({ children }) {
    const { sendAudio, sendImage, sendControl, isConnected, disconnect } = useWebSocket();
    // Text chat goes through the dedicated /ws/chat endpoint (ADK runner.run_async)
    // for reliable responses independent of the live audio session.
    const { sendText, isConnected: isChatConnected, serverSessionId, reconnect: reconnectChat } = useChatWebSocket();
    const { startRecording, stopRecording, isRecording, volume: captureVolume, permissionError: micError, clearError: clearMicError, setMuted } = useAudioCapture({
        onAudioData: sendAudio,
    });
    const { stopPlayback, volume: playbackVolume } = useAudioPlayback();

    // Video capture — frames are piped straight to the model via sendImage
    const {
        startCapture,
        stopCapture,
        isCapturing: isVideoActive,
        source: videoSource,
        getPreviewStream,
        permissionError: videoError,
        clearError: clearVideoError,
    } = useVideoCapture({ onFrameData: sendImage });

    const [isMuted, setIsMuted] = useState(false);

    // Derived booleans
    const isScreenSharing = isVideoActive && videoSource === 'screen';
    const isCameraOn = isVideoActive && videoSource === 'camera';

    // Track previous isConnected to detect disconnects
    const prevConnectedRef = useRef(isConnected);
    useEffect(() => {
        // If connection drops, tear down video capture to free hardware
        if (prevConnectedRef.current && !isConnected) {
            stopCapture();
        }
        prevConnectedRef.current = isConnected;
    }, [isConnected, stopCapture]);

    // ── Toggles ──────────────────────────────────────────────────────

    const toggleRecording = useCallback(() => {
        if (!isConnected && !isRecording) return; // Can't start if live WS disconnected
        if (isRecording) {
            stopRecording();
        } else {
            stopPlayback();
            startRecording();
        }
    }, [isRecording, isConnected, startRecording, stopRecording, stopPlayback]);

    const toggleMute = useCallback(() => {
        const next = !isMuted;
        setIsMuted(next);
        setMuted(next);
    }, [isMuted, setMuted]);

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
        if (isRecording) stopRecording();
        if (isVideoActive) {
            stopCapture();
            sendControl(isScreenSharing ? 'screen_share_stop' : 'camera_stop');
        }
    }, [isRecording, isVideoActive, isScreenSharing, stopRecording, stopCapture, sendControl]);

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
            isChatConnected,
            disconnect,
            reconnectChat,
            serverSessionId,
            // Audio state
            isRecording,
            isMuted,
            captureVolume,
            playbackVolume,
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
            toggleScreen,
            toggleCamera,
            stopPlayback,
            stopCapture,
            stopAll,
        }),
        [
            sendText, sendAudio, sendImage, sendControl, isConnected, isChatConnected, disconnect,
            reconnectChat, serverSessionId,
            isRecording, isMuted, captureVolume, playbackVolume,
            isScreenSharing, isCameraOn, isVideoActive, videoSource, getPreviewStream,
            permissionError, clearPermissionError,
            toggleRecording, toggleMute, toggleScreen, toggleCamera,
            stopPlayback, stopCapture, stopAll,
        ],
    );

    return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}

export function useVoice() {
    const ctx = useContext(VoiceContext);
    if (!ctx) throw new Error('useVoice must be used within <VoiceProvider>');
    return ctx;
}
