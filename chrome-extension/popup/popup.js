/**
 * Popup Script — Minimal UI for the extension popup.
 */

// TODO: Implement:
//   - Connect/disconnect toggle
//   - Voice interaction (via offscreen document for audio)
//   - Text input fallback
//   - Transcript display
//   - Status indicator from background service worker

const statusDot = document.getElementById('status-dot');
const voiceBtn = document.getElementById('voice-btn');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const transcript = document.getElementById('transcript');

// Check connection status
chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
  if (res?.connected) {
    statusDot.classList.remove('offline');
    statusDot.classList.add('online');
  }
});

// Send text message
sendBtn.addEventListener('click', () => {
  const text = textInput.value.trim();
  if (text) {
    chrome.runtime.sendMessage({ type: 'SEND_TEXT', text });
    textInput.value = '';
    addTranscriptLine('You', text);
  }
});

textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendBtn.click();
});

// Voice button (push-to-talk)
voiceBtn.addEventListener('mousedown', () => {
  chrome.runtime.sendMessage({ type: 'START_AUDIO' });
  voiceBtn.classList.add('active');
});

voiceBtn.addEventListener('mouseup', () => {
  chrome.runtime.sendMessage({ type: 'STOP_AUDIO' });
  voiceBtn.classList.remove('active');
});

function addTranscriptLine(role, text) {
  const line = document.createElement('div');
  line.className = `transcript-line ${role === 'You' ? 'user' : 'agent'}`;
  line.textContent = `${role}: ${text}`;
  transcript.appendChild(line);
  transcript.scrollTop = transcript.scrollHeight;
}

// Listen for responses from background
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'AGENT_RESPONSE') {
    addTranscriptLine('Omni', message.text);
  }
});
