# Track 4: Frontend Developer Guide

> **Scope**: Build and extend the Omni Hub web dashboard (React 19 + Vite).
> **Directory**: `dashboard/`
> **Stack**: React 19, Vite, Zustand 5, Tailwind CSS, Firebase Auth, WebSocket
> **Prerequisites**: React, JavaScript/JSX, basic WebSocket understanding

---

## Quick Start

```bash
cd dashboard
cp .env.example .env          # Fill in your Firebase config
pnpm install                  # Or: npm install
pnpm dev                      # Start dev server at http://localhost:5173
```

Make sure the backend is running on `http://localhost:8000`.

---

## Environment Variables

Create `dashboard/.env` from `.env.example`:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000

# Firebase Web Config (from Firebase Console → Project Settings → Web App)
VITE_FIREBASE_API_KEY=your-firebase-web-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-firebase-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=123456789
VITE_FIREBASE_APP_ID=1:123456789:web:abcdef
```

---

## Project Structure

```
dashboard/src/
├── App.jsx                    # Root component + router
├── main.jsx                   # Entry point
│
├── pages/                     # Route-level pages
│   ├── DashboardPage.jsx      # Main chat + agent interaction
│   ├── ClientsPage.jsx        # Connected clients overview
│   ├── MCPStorePage.jsx       # Plugin marketplace
│   ├── PersonasPage.jsx       # Persona management
│   ├── SessionsPage.jsx       # Session history
│   └── SettingsPage.jsx       # User settings
│
├── components/                # UI components by domain
│   ├── auth/                  # Login/signup forms
│   ├── chat/                  # Chat bubbles, input, message list
│   ├── clients/               # Client status cards
│   ├── genui/                 # GenUI rendering (agent-generated UIs)
│   ├── layout/                # Sidebar, header, page shells
│   ├── mcp/                   # Plugin cards, toggle switches
│   ├── persona/               # Persona avatars, selectors
│   ├── sandbox/               # E2B sandbox viewer
│   ├── session/               # Session cards, details
│   ├── shared/                # Reusable components
│   └── ui/                    # Base UI primitives (shadcn-style)
│
├── stores/                    # Zustand state management
│   ├── authStore.js           # User auth state + Firebase token
│   ├── chatStore.js           # Messages, agent state, tools
│   ├── agentActivityStore.js  # Agent reasoning/activity feed
│   ├── clientStore.js         # Connected clients list
│   ├── mcpStore.js            # Plugin catalog + enabled state
│   ├── personaStore.js        # Active persona, persona list
│   ├── sessionStore.js        # Session history
│   ├── themeStore.js          # Dark/light mode
│   └── uiStore.js             # Sidebar open, modals, etc.
│
├── hooks/                     # Custom React hooks
│   ├── useAuth.js             # Firebase auth lifecycle
│   ├── useBootstrap.js        # Init sequence (auth → WS → session)
│   ├── useChatWebSocket.js    # Text-only WS connection
│   ├── useWebSocket.js        # Audio+text WS connection
│   ├── useAudioCapture.js     # Microphone → PCM stream
│   ├── useAudioPlayback.js    # PCM → speaker output
│   ├── useVideoCapture.js     # Camera capture
│   ├── useFirestore.js        # Firestore real-time queries
│   ├── useKeyboard.js         # Keyboard shortcuts
│   ├── useMediaQuery.js       # Responsive breakpoints
│   ├── useDocumentTitle.js    # Dynamic page titles
│   └── useDraggable.js        # Drag & drop utility
│
├── lib/                       # Utility functions
└── styles/                    # Global CSS / Tailwind config
```

---

## State Management (Zustand)

Each store is a standalone Zustand slice. Import directly:

```jsx
import { useChatStore } from '@/stores/chatStore';

function ChatMessages() {
  const messages = useChatStore(s => s.messages);
  const agentState = useChatStore(s => s.agentState);

  return (
    <div>
      {agentState === 'processing' && <Spinner />}
      {messages.map(msg => <MessageBubble key={msg.id} msg={msg} />)}
    </div>
  );
}
```

### Key stores to understand

| Store | What it manages |
|-------|----------------|
| `authStore` | `user`, `token`, `isAuthenticated`, `login()`, `logout()` |
| `chatStore` | `messages`, `agentState`, `addMessage()`, `setAgentState()` |
| `agentActivityStore` | `activities`, `addActivity()` — sub-agent calls, reasoning |
| `mcpStore` | `catalog`, `enabledPlugins`, `toggle()` |
| `clientStore` | `onlineClients`, `setClients()` |
| `personaStore` | `activePersona`, `personas`, `switchPersona()` |

---

## WebSocket Integration

The dashboard connects to the backend via WebSocket. Two hooks:

### `useChatWebSocket` — text-only

```jsx
// Simplified usage
const { sendMessage, isConnected } = useChatWebSocket();

sendMessage("What's the weather?");
```

Internally this hook:
1. Opens WS to `VITE_WS_URL/ws/chat`
2. Sends auth message with Firebase token
3. Routes incoming messages to the appropriate store
4. Handles reconnection on disconnect

### `useWebSocket` — audio + text

Used by the voice mode on `/ws/live`. Adds binary frames for PCM audio.

---

## WS Message Types to Handle

When building new frontend features, map these server messages to UI:

| Message Type | Store Target | UI Component |
|-------------|-------------|--------------|
| `response` | `chatStore.addMessage()` | Chat bubble |
| `transcription` | `chatStore` | Live transcription text |
| `tool_call` | `chatStore` | Tool activity card |
| `tool_response` | `chatStore` | Tool result card |
| `image_response` | `chatStore` | Image display |
| `agent_activity` | `agentActivityStore` | Activity feed |
| `status` | `chatStore.setAgentState()` | Loading indicator |
| `error` | toast / `chatStore` | Error banner |
| `persona_changed` | `personaStore` | Persona avatar update |
| `cross_client` | `clientStore` | Cross-device action UI |

---

## Adding a New Page

1. Create `src/pages/MyPage.jsx`
2. Add route in `src/App.jsx`
3. Add navigation link in `src/components/layout/`

```jsx
// src/pages/MyPage.jsx
export default function MyPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">My New Page</h1>
    </div>
  );
}
```

---

## GenUI Rendering

The agent can return `content_type: "genui"` with a JSON UI spec. The `components/genui/` directory contains renderers:

```json
{
  "type": "response",
  "content_type": "genui",
  "genui": {
    "type": "card",
    "title": "Weather in Tokyo",
    "fields": [
      {"label": "Temperature", "value": "22°C"},
      {"label": "Condition", "value": "Sunny"}
    ]
  }
}
```

Build new GenUI components in `components/genui/` and register them in the GenUI renderer.

---

## REST API Calls

Use `fetch` with the auth token for REST endpoints:

```jsx
import { useAuthStore } from '@/stores/authStore';

async function fetchPlugins() {
  const token = useAuthStore.getState().token;
  const res = await fetch(`${import.meta.env.VITE_API_URL}/api/v1/plugins/catalog`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
}
```

---

## Styling

- **Tailwind CSS** for all styling — no CSS modules
- **`tailwind-merge`** + **`clsx`** for conditional classes
- **`lucide-react`** for icons (same icon set as plugin `icon` field)
- UI primitives in `components/ui/` (shadcn/ui-style)

---

## Scripts

```bash
pnpm dev              # Dev server with hot reload
pnpm build            # Production build → dist/
pnpm preview          # Preview production build
pnpm lint             # ESLint check
pnpm lint:fix         # Auto-fix lint issues
pnpm format           # Prettier format
pnpm format:check     # Check formatting
```

---

## Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| React | 19 | UI framework |
| Vite | latest | Build tool / dev server |
| Zustand | 5 | State management |
| Firebase | 11 | Authentication |
| Tailwind CSS | 4 | Utility-first CSS |
| react-router | 7 | Client-side routing |
| react-markdown | 9 | Render agent markdown responses |
| recharts | 2 | Charts/graphs |
| lucide-react | latest | Icon library |
| sonner | 1 | Toast notifications |
| cmdk | 1 | Command palette (⌘K) |

---

## FAQ

**Q: How do I get a Firebase token for testing?**
A: Login through the dashboard UI, then in browser devtools: `await firebase.auth().currentUser.getIdToken()`.

**Q: Where do I add new message type handling?**
A: In the WebSocket hook (`useChatWebSocket.js` or `useWebSocket.js`), add a case for the new `msg.type` and dispatch to the appropriate store.

**Q: How do I add a new Zustand store?**
A: Create `src/stores/myStore.js`, export a `useMyStore` hook. Follow existing patterns in `chatStore.js`.

**Q: Can I use a different UI library?**
A: The project uses custom Tailwind components (shadcn-style). You can add component libraries but keep the design consistent.
