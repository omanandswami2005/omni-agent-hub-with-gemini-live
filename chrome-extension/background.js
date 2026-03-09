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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Route messages between components
  if (message.type === 'CONNECT') {
    // TODO: Establish WS connection
  } else if (message.type === 'SEND_TEXT') {
    // TODO: Forward to server
  } else if (message.type === 'GET_STATUS') {
    sendResponse({ connected: ws?.readyState === WebSocket.OPEN });
  }
  return true; // Keep channel open for async response
});
