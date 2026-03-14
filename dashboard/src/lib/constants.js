/**
 * Application constants.
 */

export const APP_NAME = 'Omni';
export const APP_TAGLINE = 'Speak anywhere. Act everywhere.';

export const WS_RECONNECT_MIN_MS = 1000;
export const WS_RECONNECT_MAX_MS = 30000;

export const AUDIO_CAPTURE_RATE = 16000;
export const AUDIO_PLAYBACK_RATE = 24000;

export const VIDEO_CAPTURE_FPS = 2;
export const VIDEO_CAPTURE_QUALITY = 0.7;
export const VIDEO_MAX_DIMENSION = 1024;

export const AGENT_STATES = {
  IDLE: 'idle',
  LISTENING: 'listening',
  THINKING: 'thinking',
  SPEAKING: 'speaking',
  TOOL_USE: 'tool_use',
};

export const CLIENT_TYPES = {
  WEB: 'web_dashboard',
  MOBILE: 'mobile_pwa',
  CHROME: 'chrome_extension',
  DESKTOP: 'desktop_python',
  ESP32: 'esp32_device',
};

/**
 * Returns the correct client_type string to send in the WS auth handshake.
 * Mobile browsers (phone/tablet) send "mobile" so they occupy a separate
 * slot in ConnectionManager from desktop browsers which send "web".
 */
export function getClientType() {
  const ua = navigator.userAgent;
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|mobile|CriOS/i.test(ua);
  // Also treat narrow-screen as mobile (PWA installed on phone)
  const isNarrow = window.screen.width <= 768;
  return isMobile || isNarrow ? 'mobile' : 'web';
}

export const ROUTES = {
  HOME: '/',
  PERSONAS: '/personas',
  MCP_STORE: '/mcp-store',
  SESSIONS: '/sessions',
  SETTINGS: '/settings',
  CLIENTS: '/clients',
};
