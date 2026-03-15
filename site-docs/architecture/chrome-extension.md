# Chrome Extension Architecture

The Omni Chrome Extension enables browser-based voice interaction and page-level AI actions.

## Components

```
chrome-extension/
├── manifest.json       # Extension manifest (MV3)
├── background.js       # Service worker
├── content.js          # Content script (injected into pages)
├── popup/
│   ├── popup.html      # Extension popup UI
│   ├── popup.js        # Popup logic
│   └── popup.css       # Popup styles
├── offscreen/
│   ├── offscreen.html  # Offscreen document for audio
│   └── offscreen.js    # Audio capture/playback
└── icons/              # Extension icons
```

## How It Works

1. **Popup** — Click the extension icon to open a chat interface
2. **Voice** — Uses the offscreen document to capture microphone audio and stream it over WebSocket
3. **Page Actions** — Content script can extract page data, fill forms, or interact with DOM elements
4. **Background** — Service worker manages WebSocket connection lifecycle and message routing
