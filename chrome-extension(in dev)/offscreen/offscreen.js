/**
 * Offscreen Script — Audio capture/playback for Chrome Extension.
 *
 * Chrome MV3 service workers can't access getUserMedia or AudioContext.
 * This offscreen document handles all audio I/O and forwards PCM
 * data to/from the background script via chrome.runtime messaging.
 */

// TODO: Implement:
//   - AudioWorklet-based capture (16kHz PCM16, same as dashboard)
//   - AudioContext playback (24kHz PCM16 from server)
//   - Message bridge: background ↔ offscreen for audio data
//   - Start/stop audio on demand from background

let audioContext = null;
let mediaStream = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.type) {
        case 'START_AUDIO':
            startAudioCapture();
            sendResponse({ success: true });
            break;

        case 'STOP_AUDIO':
            stopAudioCapture();
            sendResponse({ success: true });
            break;

        case 'PLAY_AUDIO':
            // message.data = ArrayBuffer of PCM16 at 24kHz
            playAudioChunk(message.data);
            sendResponse({ success: true });
            break;
    }
    return true;
});

async function startAudioCapture() {
    // TODO: getUserMedia → AudioWorklet → PCM16 chunks → chrome.runtime.sendMessage
}

function stopAudioCapture() {
    mediaStream?.getTracks().forEach((t) => t.stop());
    mediaStream = null;
}

function playAudioChunk(pcm16Buffer) {
    // TODO: Decode PCM16 → Float32 → AudioBufferSourceNode → play
}
