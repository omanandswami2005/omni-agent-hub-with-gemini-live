/**
 * useVideoCapture — Camera / Screen → Canvas → JPEG frames → callback.
 *
 * Mirrors the useAudioCapture pattern: start/stop with a continuous
 * frame loop that pushes base64 JPEG data to the caller via onFrameData.
 *
 * Lifecycle:
 *  1. startCapture('camera' | 'screen')  → acquires stream, starts frame loop
 *  2. Frame loop: video → canvas → toBlob(jpeg) → base64 → onFrameData(b64, mime)
 *  3. stopCapture()  → stops tracks, clears interval, revokes resources
 *  4. Auto-cleanup on unmount or when the user clicks "Stop sharing" in browser chrome
 *
 * Permission errors (DOMException names):
 *  - NotAllowedError  → user clicked "Block" or "Never allow" (or dismissed with ESC for screen)
 *  - NotFoundError    → no camera/screen device available
 *  - NotReadableError → device already in use by another app
 *  - SecurityError    → insecure context (non-HTTPS outside localhost)
 */

import { useRef, useState, useCallback, useEffect } from 'react';

const DEFAULT_FPS = 1;
const DEFAULT_QUALITY = 0.7;
const MAX_DIMENSION = 1024;

/**
 * Classify a MediaDevices error into a user-facing error object.
 * Returns null when the user simply cancelled the screen-share picker
 * (which also throws NotAllowedError but has no meaningful recovery).
 */
function classifyError(err, src) {
    const name = err?.name || '';
    if (name === 'NotAllowedError') {
        // Screen share picker cancelled by user — silent, no toast needed
        if (src === 'screen') return null;
        return {
            type: 'denied',
            device: src === 'camera' ? 'camera' : 'microphone',
            title: `${src === 'camera' ? 'Camera' : 'Microphone'} access blocked`,
            message:
                'You previously blocked access. Click the camera icon in your browser\u2019s address bar and choose \u201cAllow\u201d, then retry.',
        };
    }
    if (name === 'NotFoundError') {
        return {
            type: 'not_found',
            device: src,
            title: `No ${src === 'camera' ? 'camera' : 'screen'} found`,
            message: `No ${src === 'camera' ? 'camera device' : 'capturable screen'} was detected. Connect a device and try again.`,
        };
    }
    if (name === 'NotReadableError' || name === 'AbortError') {
        return {
            type: 'busy',
            device: src,
            title: `${src === 'camera' ? 'Camera' : 'Screen'} unavailable`,
            message: `The ${src === 'camera' ? 'camera' : 'screen'} is already in use by another application. Close it and retry.`,
        };
    }
    if (name === 'SecurityError') {
        return {
            type: 'security',
            device: src,
            title: 'Insecure context',
            message: 'Media capture requires HTTPS. Open the app over a secure connection.',
        };
    }
    // Unexpected error — surface it
    return {
        type: 'unknown',
        device: src,
        title: `Couldn't start ${src === 'camera' ? 'camera' : 'screen share'}`,
        message: err?.message || 'An unexpected error occurred.',
    };
}

function fitDimensions(w, h, maxDim) {
    if (w <= maxDim && h <= maxDim) return { width: w, height: h };
    const ratio = Math.min(maxDim / w, maxDim / h);
    return { width: Math.round(w * ratio), height: Math.round(h * ratio) };
}

export function useVideoCapture({ onFrameData, fps = DEFAULT_FPS, quality = DEFAULT_QUALITY } = {}) {
    const [source, setSource] = useState(null);
    const [isCapturing, setIsCapturing] = useState(false);
    const [permissionError, setPermissionError] = useState(null); // { type, device, title, message }
    const streamRef = useRef(null);
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const intervalRef = useRef(null);
    const onFrameDataRef = useRef(onFrameData);

    useEffect(() => { onFrameDataRef.current = onFrameData; }, [onFrameData]);

    const clearError = useCallback(() => setPermissionError(null), []);

    // ── Start ──────────────────────────────────────────────────────────
    const startCapture = useCallback(async (src = 'camera') => {
        // Clear any previous error on retry
        setPermissionError(null);
        stopCapture();

        try {
            const stream = src === 'screen'
                ? await navigator.mediaDevices.getDisplayMedia({ video: true })
                : await navigator.mediaDevices.getUserMedia({
                    video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
                });

            streamRef.current = stream;

            const video = document.createElement('video');
            video.srcObject = stream;
            video.muted = true;
            video.playsInline = true;
            videoRef.current = video;

            await video.play();

            await new Promise((resolve) => {
                if (video.videoWidth > 0) return resolve();
                video.onloadedmetadata = resolve;
            });

            const { width, height } = fitDimensions(video.videoWidth, video.videoHeight, MAX_DIMENSION);
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            canvasRef.current = canvas;

            const ctx = canvas.getContext('2d');
            const frameInterval = 1000 / fps;

            intervalRef.current = setInterval(() => {
                if (video.readyState < video.HAVE_CURRENT_DATA) return;
                ctx.drawImage(video, 0, 0, width, height);
                canvas.toBlob(
                    (blob) => {
                        if (!blob) return;
                        const reader = new FileReader();
                        reader.onloadend = () => {
                            const b64 = reader.result.split(',')[1];
                            onFrameDataRef.current?.(b64, 'image/jpeg');
                        };
                        reader.readAsDataURL(blob);
                    },
                    'image/jpeg',
                    quality,
                );
            }, frameInterval);

            // Browser "Stop sharing" chrome auto-cleanup
            stream.getVideoTracks().forEach((track) => {
                track.addEventListener('ended', () => stopCapture());
            });

            setSource(src);
            setIsCapturing(true);
        } catch (err) {
            const classified = classifyError(err, src);
            if (classified) setPermissionError(classified);
            setSource(null);
            setIsCapturing(false);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [fps, quality]);

    // ── Stop ───────────────────────────────────────────────────────────
    const stopCapture = useCallback(() => {
        clearInterval(intervalRef.current);
        intervalRef.current = null;

        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;

        if (videoRef.current) {
            videoRef.current.pause();
            videoRef.current.srcObject = null;
            videoRef.current = null;
        }

        canvasRef.current = null;
        setSource(null);
        setIsCapturing(false);
    }, []);

    const getPreviewStream = useCallback(() => streamRef.current, []);

    useEffect(() => {
        return () => stopCapture();
    }, [stopCapture]);

    return { startCapture, stopCapture, isCapturing, source, getPreviewStream, permissionError, clearError };
}
