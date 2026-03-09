/**
 * Application constants.
 */

export const APP_NAME = 'Omni';
export const APP_TAGLINE = 'Speak anywhere. Act everywhere.';

export const WS_RECONNECT_MIN_MS = 1000;
export const WS_RECONNECT_MAX_MS = 30000;

export const AUDIO_CAPTURE_RATE = 16000;
export const AUDIO_PLAYBACK_RATE = 24000;

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

export const ROUTES = {
  HOME: '/',
  PERSONAS: '/personas',
  MCP_STORE: '/mcp-store',
  SESSIONS: '/sessions',
  SETTINGS: '/settings',
  CLIENTS: '/clients',
};
