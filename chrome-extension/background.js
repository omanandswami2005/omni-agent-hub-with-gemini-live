/**
 * Background Service Worker — Chrome Extension.
 *
 * Manages WebSocket connection to Omni server, routes messages
 * between popup, content scripts, and offscreen document.
 */

// TODO: Implement:
//   - WebSocket connection to server (raw WS, same protocol as dashboard)
//   - Message routing: content script ↔ server ↔ popup
//   - Offscreen document management for audio capture/playback
//   - Tab management for cross-client actions (open URL, read page, etc.)
//   - Context menu integration
//   - Badge updates for connection status

let ws = null;

chrome.runtime.onInstalled.addListener(() => {
  console.log('Omni extension installed');
});

// Forward server-pushed messages to the popup
function forwardToPopup(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {
    // Popup not open — safe to ignore
  });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Route messages between components
  if (message.type === 'CONNECT') {
    // TODO: Establish WS connection
  } else if (message.type === 'SEND_TEXT') {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'text', content: message.text }));
    }
  } else if (message.type === 'GET_STATUS') {
    sendResponse({ connected: ws?.readyState === WebSocket.OPEN });
  }
  return true; // Keep channel open for async response
});

// Handle incoming WebSocket messages from the server
function handleServerMessage(data) {
  try {
    const msg = JSON.parse(data);
    if (msg.type === 'session_suggestion') {
      forwardToPopup({
        type: 'SESSION_SUGGESTION',
        session_id: msg.session_id || '',
        available_clients: msg.available_clients || [],
        message: msg.message || '',
      });
    } else if (msg.type === 'client_status_update') {
      forwardToPopup({ type: 'CLIENT_STATUS', clients: msg.clients || [] });
    } else if (msg.type === 'response' && msg.data) {
      forwardToPopup({ type: 'AGENT_RESPONSE', text: msg.data });
    }
  } catch {
    // Non-JSON — ignore
  }
}
