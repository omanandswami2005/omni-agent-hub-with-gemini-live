# OpenUI — The Open Standard for Generative UI

> **Source**: [github.com/thesysdev/openui](https://github.com/thesysdev/openui)
> **Docs**: [openui.com](https://openui.com/) · [Playground](https://www.openui.com/playground)
> **License**: MIT · **Stars**: 631 · **Language**: TypeScript (86%) · **By**: [TheSys](https://thesys.dev/)

---

## 1. What Is OpenUI?

OpenUI is a **full-stack Generative UI (GenUI) framework** built around **OpenUI Lang** — a compact, streaming-first language designed for LLM-generated UI. Instead of treating model output as only text (or bloated JSON), OpenUI lets you:

1. **Define** a component library with typed props (Zod schemas)
2. **Generate** a system prompt from that library → tells the model exactly what components it can emit
3. **Stream** the model's output as OpenUI Lang tokens
4. **Render** those tokens progressively into React components in real time

### Core Value Proposition

| Feature | Description |
|---|---|
| **OpenUI Lang** | A compact DSL that is **up to 67% more token-efficient** than equivalent JSON formats |
| **Streaming-first** | Parse and render progressively as tokens arrive — no waiting for complete response |
| **Controlled output** | Model can ONLY emit components you registered — no arbitrary HTML/JS injection |
| **Typed contracts** | Zod schemas enforce prop types at definition time |
| **Built-in libraries** | Charts, forms, tables, layouts, images, cards — 30+ components ready to use |
| **Chat surfaces** | `FullScreen`, `Copilot`, `BottomTray` — drop-in chat UIs |
| **Model-agnostic** | Works with any LLM (OpenAI, Gemini, Claude, etc.) via streaming adapters |

---

## 2. Architecture & How It Works

```
┌──────────────────────────────────────────────────────────────┐
│   1. DEFINE                                                   │
│   defineComponent({ name, props: z.object(...), component })  │
│   createLibrary({ components: [...] })                        │
│                                                               │
│   2. GENERATE PROMPT                                          │
│   library.prompt({ preamble, additionalRules, examples })     │
│   → System prompt instructs LLM what components to emit       │
│                                                               │
│   3. LLM GENERATES OpenUI Lang                                │
│   <Card title="Weather"> <Text>Sunny, 72°F</Text> </Card>    │
│                                                               │
│   4. STREAM & RENDER                                          │
│   <Renderer response={stream} library={lib} isStreaming />    │
│   → Progressive React rendering as tokens arrive              │
└──────────────────────────────────────────────────────────────┘
```

### Key Insight

The LLM never generates raw HTML/JSX. It generates **OpenUI Lang** — a constrained DSL where every tag maps to a registered component. The `<Renderer>` parses this incrementally and renders React components. This gives you:

- **Safety**: No arbitrary code execution, no XSS
- **Token efficiency**: 52-67% fewer tokens than JSON
- **Streaming**: UI appears progressively, not after full response
- **Consistency**: Output always matches your design system

---

## 3. Package Breakdown

### 3.1 `@openuidev/react-lang` — Core Runtime

The foundational package. Handles component definitions, prompt generation, parsing, and rendering.

**Install**: `npm install @openuidev/react-lang`
**Peer deps**: `react >=19.0.0`

#### Define a Component

```jsx
import { defineComponent } from "@openuidev/react-lang";
import { z } from "zod";

const Greeting = defineComponent({
  name: "Greeting",
  description: "Displays a greeting message",
  props: z.object({
    name: z.string().describe("The person's name"),
    mood: z.enum(["happy", "excited"]).optional().describe("Tone of the greeting"),
  }),
  component: ({ name, mood }) => (
    <div className={mood === "excited" ? "text-xl font-bold" : ""}>
      Hello, {name}!
    </div>
  ),
});
```

#### Create a Library

```jsx
import { createLibrary } from "@openuidev/react-lang";

const library = createLibrary({
  components: [Greeting, Card, Table, Chart /* ... */],
  root: "Card", // optional default root component
});
```

#### Generate a System Prompt

```jsx
const systemPrompt = library.prompt({
  preamble: "You are a helpful assistant.",
  additionalRules: ["Always greet the user by name."],
  examples: ["<Greeting name='Alice' mood='happy' />"],
});
// → This becomes the system prompt sent to the LLM
```

#### Render Streamed Output

```jsx
import { Renderer } from "@openuidev/react-lang";

function AssistantMessage({ response, isStreaming }) {
  return (
    <Renderer
      response={response}
      library={library}
      isStreaming={isStreaming}
      onAction={(event) => console.log("Action:", event)}
    />
  );
}
```

#### Key APIs

| API | Purpose |
|---|---|
| `defineComponent(config)` | Define a component with name, Zod props, description, React renderer |
| `createLibrary(definition)` | Create a library from an array of defined components |
| `library.prompt(options)` | Generate system prompt instructing the LLM |
| `library.toJSONSchema()` | Export JSON Schema of all components |
| `<Renderer>` | Progressive streaming React renderer |
| `createParser(library)` | One-shot parser for complete OpenUI Lang text |
| `createStreamingParser(library)` | Incremental parser for streaming input |

#### Context Hooks (for use inside component renderers)

| Hook | Purpose |
|---|---|
| `useIsStreaming()` | Whether the model is still streaming |
| `useRenderNode()` | Render child element nodes |
| `useTriggerAction()` | Trigger an action event (button clicks, form submits) |
| `useGetFieldValue()` | Get a form field's current value |
| `useSetFieldValue()` | Set a form field's value |
| `useFormValidation()` | Access form validation state |

---

### 3.2 `@openuidev/react-headless` — Chat State & Streaming

Headless React primitives for chat — state management, streaming adapters, and message format converters. **No UI imposed** — bring your own design.

**Install**: `npm install @openuidev/react-headless`
**Peer deps**: `react >=19.0.0`, `react-dom >=19.0.0`, `zustand ^4.5.5`

#### URL-Based Setup (Simplest)

```jsx
import { ChatProvider } from "@openuidev/react-headless";

function App() {
  return (
    <ChatProvider apiUrl="/api/chat" threadApiUrl="/api/threads">
      <YourChatUI />
    </ChatProvider>
  );
}
```

#### Custom Functions (Full Control)

```jsx
<ChatProvider
  processMessage={async ({ threadId, messages, abortController }) => {
    return fetch("/api/chat", {
      method: "POST",
      body: JSON.stringify({ threadId, messages }),
      signal: abortController.signal,
    });
  }}
  fetchThreadList={async () => { /* ... */ }}
  createThread={async (firstMessage) => { /* ... */ }}
>
  <YourChatUI />
</ChatProvider>
```

#### Hooks

| Hook | Returns | Purpose |
|---|---|---|
| `useThread()` | `ThreadState & ThreadActions` | Access messages, send, cancel, streaming state |
| `useThreadList()` | `ThreadListState & ThreadListActions` | Manage multiple conversations |
| `useMessage()` | `{ message }` | Access current message inside a message component |

#### Streaming Adapters

| Adapter | Source |
|---|---|
| `agUIAdapter` | Default — AG-UI SSE events |
| `openAIAdapter` | OpenAI Chat Completions streaming |
| `openAIResponsesAdapter` | OpenAI Responses API streaming |
| `openAIReadableStreamAdapter` | OpenAI SDK NDJSON output |
| Custom | Implement `StreamProtocolAdapter` interface |

#### Message Formats

| Format | Converts to/from |
|---|---|
| `identityMessageFormat` | No conversion (AG-UI format) |
| `openAIMessageFormat` | OpenAI `ChatCompletionMessageParam[]` |
| `openAIConversationMessageFormat` | OpenAI Responses API `ResponseInputItem[]` |
| Custom | Implement `MessageFormat` interface |

---

### 3.3 `@openuidev/react-ui` — Prebuilt Chat & Components

Drop-in chat layouts and two built-in component libraries with theming.

**Install**: `npm install @openuidev/react-ui @openuidev/react-lang @openuidev/react-headless`

#### Chat Layouts

```jsx
import { FullScreen } from "@openuidev/react-ui";
import "@openuidev/react-ui/components.css";

// Full-page chat with thread sidebar
function App() {
  return <FullScreen apiUrl="/api/chat" threadApiUrl="/api/threads" />;
}
```

| Layout | Description |
|---|---|
| `FullScreen` | Full-page chat with thread sidebar |
| `Copilot` | Side-panel copilot overlay |
| `BottomTray` | Collapsible bottom tray chat |

#### Built-in Component Libraries

| Library | Description |
|---|---|
| `openuiLibrary` | Full — charts, tables, forms, cards, images, and more |
| `openuiChatLibrary` | Chat-optimized subset with follow-ups, steps, callouts |

```jsx
import { Renderer } from "@openuidev/react-lang";
import { openuiLibrary, openuiPromptOptions } from "@openuidev/react-ui";

// Generate a system prompt from the built-in library
const systemPrompt = openuiLibrary.prompt(openuiPromptOptions);

// Render model output
function AssistantMessage({ content, isStreaming }) {
  return (
    <Renderer response={content} library={openuiLibrary} isStreaming={isStreaming} />
  );
}
```

#### Available UI Components (30+)

| Category | Components |
|---|---|
| **Layout** | Card, CardHeader, SectionBlock, Tabs, Accordion, Carousel, Separator, Steps |
| **Data Display** | Table, Charts (bar, line, area, pie, radar, scatter), ListBlock, ListItem, Tag, TagBlock, CodeBlock, Image, ImageBlock, ImageGallery |
| **Forms** | Input, TextArea, Select, CheckBoxGroup, RadioGroup, SwitchGroup, Slider, DatePicker, FormControl, Label |
| **Actions** | Button, Buttons, IconButton, FollowUpBlock, FollowUpItem |
| **Feedback** | Callout, TextCallout, MessageLoading |
| **Content** | TextContent, MarkDownRenderer |
| **Chat** | FullScreen, Copilot, BottomTray, Shell.*, CopilotShell.*, ToolCall, ToolResult |

#### Theming

```jsx
import { ThemeProvider, createTheme } from "@openuidev/react-ui";

const customTheme = createTheme({
  primary: "#6366f1",
  background: "#fafafa",
  foreground: "#1a1a1a",
});

function App() {
  return (
    <ThemeProvider mode="light" lightTheme={customTheme}>
      <YourApp />
    </ThemeProvider>
  );
}
```

---

### 3.4 `@openuidev/cli` — Scaffolding & Prompt Generation

CLI for scaffolding apps and generating system prompts from component libraries.

**Install**: `npx @openuidev/cli --help`

#### Commands

| Command | Purpose |
|---|---|
| `openui create --name my-app` | Scaffold a new Next.js app with OpenUI Chat |
| `openui generate ./src/library.ts` | Generate system prompt from a library file |
| `openui generate ./src/library.ts --json-schema` | Generate JSON Schema instead |
| `openui generate ./src/library.ts --out prompt.txt` | Write to file |

---

## 4. Token Efficiency Benchmarks

Measured with `tiktoken` (GPT-5 encoder). OpenUI Lang vs two JSON-based streaming formats:

| Scenario | Thesys C1 JSON | Vercel JSONL | OpenUI Lang | vs C1 | vs Vercel |
|---|---|---|---|---|---|
| simple-table | 340 | 357 | 148 | **-56.5%** | -58.5% |
| chart-with-data | 520 | 516 | 231 | **-55.6%** | -55.2% |
| contact-form | 893 | 849 | 294 | **-67.1%** | -65.4% |
| dashboard | 2247 | 2261 | 1226 | -45.4% | -45.8% |
| pricing-page | 2487 | 2379 | 1195 | **-52.0%** | -49.8% |
| settings-panel | 1244 | 1205 | 540 | **-56.6%** | -55.2% |
| e-commerce-product | 2449 | 2381 | 1166 | **-52.4%** | -51.0% |
| **TOTAL** | **10180** | **9948** | **4800** | **-52.8%** | **-51.7%** |

---

## 5. Relevance to Our Project (Omni Hub)

### 5.1 What We Currently Have

Our project already implements a **custom GenUI system** in `dashboard/src/components/genui/`:

| Component | Purpose |
|---|---|
| `GenUIRenderer.jsx` | Dynamic renderer dispatching by type (chart, table, card, etc.) |
| `DynamicChart.jsx` | Recharts-based charts (line, bar, area, pie) |
| `DataTable.jsx` | Dynamic sortable tables |
| `InfoCard.jsx` | Rich information cards |
| `CodeBlock.jsx` | Code display with copy button |
| `ImageGallery.jsx` | Image grid display |
| `TimelineView.jsx` | Vertical event timeline |
| `MarkdownRenderer.jsx` | Markdown with GFM support |
| `DiffViewer.jsx` | Side-by-side diff |
| `WeatherWidget.jsx` | Weather display |
| `MapView.jsx` | Google Maps embed |

Our backend pushes GenUI via `AgentResponse` with `content_type: "genui"` and a `genui` dict containing `{ type, data }`. The `MessageBubble` renders this inline in chat.

### 5.2 How OpenUI Could Enhance Our GenUI

#### Option A: Adopt OpenUI as Our GenUI Renderer (Recommended for v2)

Replace our custom `GenUIRenderer` with OpenUI's `<Renderer>` and define our components using `defineComponent`:

```jsx
// Define our existing components as OpenUI components
const WeatherWidget = defineComponent({
  name: "WeatherWidget",
  description: "Shows weather information for a location",
  props: z.object({
    location: z.string(),
    temp: z.number(),
    condition: z.string(),
    icon: z.string().optional(),
  }),
  component: ({ location, temp, condition, icon }) => (
    <div className="flex items-center gap-4 rounded-lg border p-4">
      <span className="text-4xl">{icon || '🌤️'}</span>
      <div>
        <p className="font-medium">{location}</p>
        <p className="text-2xl font-bold">{temp}°</p>
        <p className="text-sm text-muted-foreground">{condition}</p>
      </div>
    </div>
  ),
});

const omniLibrary = createLibrary({
  components: [WeatherWidget, DynamicChart, DataTable, CodeBlock, /* ... */],
});

// Generate system prompt from our component library
const genUIPrompt = omniLibrary.prompt({
  preamble: "When the user asks for data visualization, use these components.",
});
```

**Benefits**:
- **Streaming rendering** — UI appears token-by-token instead of waiting for full JSON
- **52-67% fewer tokens** — OpenUI Lang vs our current JSON-based `genui` payloads
- **Type safety** — Zod schemas enforce prop types
- **Prompt auto-generation** — `library.prompt()` creates the system instruction automatically
- **Controlled output** — Model can only emit registered components

**Challenges**:
- We use **WebSocket streaming** (not HTTP SSE) — would need a custom `StreamProtocolAdapter`
- Our backend is Python (ADK) — OpenUI is React-focused; the LLM output format (OpenUI Lang) would need to be understood by our Python backend or passed through transparently
- Our Live API is audio-first — GenUI is triggered by tool calls, not direct LLM output

#### Option B: Use OpenUI's Built-in Component Library Only (Quick Win)

Keep our current architecture but use `@openuidev/react-ui` components as drop-in replacements:

```jsx
import { Card, Table, Charts, CodeBlock } from "@openuidev/react-ui";
import "@openuidev/react-ui/components.css";
```

**Benefits**: Better component quality, theming, and consistency. Minimal refactor.

#### Option C: Use OpenUI's `react-headless` for Chat State (Future)

Replace our Zustand chat store with OpenUI's `ChatProvider` + `useThread()`:

```jsx
import { ChatProvider, useThread } from "@openuidev/react-headless";
```

**Benefits**: Built-in multi-thread management, streaming state, abort control.
**Challenge**: We have a custom WebSocket transport, not REST API.

### 5.3 Recommended Strategy for Hackathon

**For the hackathon deadline (March 17, 2026)**: Keep our current custom GenUI system. It works, it's already integrated, and it's simpler for demo purposes.

**For post-hackathon / production**: Adopt OpenUI progressively:
1. First: Replace individual components with `@openuidev/react-ui` equivalents
2. Then: Define our component library using `defineComponent` + `createLibrary`
3. Then: Use `library.prompt()` to auto-generate the GenUI system instruction
4. Finally: Implement a custom WebSocket `StreamProtocolAdapter` for our transport

### 5.4 Integration Architecture (Post-Hackathon)

```
┌─────────────────────────────────────────────────────────────────┐
│ Backend (Python / ADK)                                          │
│                                                                 │
│  Agent receives user request                                    │
│    → Tool call: generate_genui(prompt)                          │
│    → Tool uses Gemini with OpenUI Lang system prompt             │
│    → Gemini outputs OpenUI Lang tokens                          │
│    → Backend streams tokens via WebSocket                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ WebSocket Transport                                             │
│  { type: "genui_stream", content: "<Card title='...'>" }       │
│  { type: "genui_stream", content: "<Table>..." }                │
│  { type: "genui_done" }                                         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Frontend (React 19 / OpenUI)                                    │
│                                                                 │
│  Custom WebSocket StreamProtocolAdapter                         │
│    → Feeds tokens to <Renderer>                                 │
│    → Progressive rendering via omniLibrary                      │
│    → Charts, tables, cards appear as tokens arrive              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. OpenUI Lang — The Language

OpenUI Lang is a **line-oriented DSL** that looks like JSX but is optimized for streaming:

```
<Card title="Weather Report">
  <Text>Current conditions for San Francisco</Text>
  <WeatherWidget location="San Francisco" temp={72} condition="Sunny" icon="☀️" />
  <Chart type="line" data={[{day:"Mon",temp:68},{day:"Tue",temp:72}]} />
</Card>
```

### Why Not JSON?

| Metric | JSON (C1) | JSON (Vercel JSONL) | OpenUI Lang |
|---|---|---|---|
| Tokens (avg) | 10,180 | 9,948 | **4,800** |
| Streaming | Needs JSON patches | RFC 6902 patches | Native — emit and render |
| Safety | Any shape possible | Any shape possible | Only registered components |
| Parse complexity | Full JSON parser | JSONL + JSON Patch | Lightweight streaming parser |

---

## 7. Comparison: Our Current GenUI vs OpenUI

| Aspect | Our Current GenUI | With OpenUI |
|---|---|---|
| **Output format** | JSON `{ type, data }` | OpenUI Lang DSL |
| **Token cost** | Higher (full JSON) | 52-67% less |
| **Streaming** | Wait for full JSON | Progressive token-by-token |
| **Component safety** | Runtime type check | Compile-time Zod schemas |
| **Prompt generation** | Manual system instructions | Auto from `library.prompt()` |
| **Component count** | 10 custom | 30+ built-in + custom |
| **Theming** | Tailwind manual | `ThemeProvider` + `createTheme` |
| **Chat state** | Custom Zustand store | `ChatProvider` + hooks |
| **Multi-thread** | Not implemented | Built-in `useThreadList()` |
| **Form handling** | Not implemented | Built-in validation + state |

---

## 8. Key Takeaways

1. **OpenUI solves the GenUI problem formally** — It's not just a component library; it's a complete protocol (language + parser + renderer + prompt generator) for LLM → UI.

2. **Token efficiency is significant** — 52-67% reduction means faster TTFT, lower cost, and more context budget for actual conversation.

3. **Streaming is the killer feature** — Users see UI building progressively instead of waiting for a complete response. This is especially impactful for complex UIs (dashboards, forms, data tables).

4. **Compatible with our stack** — React 19 (peer dep), Zustand (used by react-headless), MIT license. Our current component library could be wrapped in `defineComponent`.

5. **Not a direct ADK integration** — OpenUI is frontend-focused. The backend just needs to get the LLM to output OpenUI Lang (via the generated system prompt). This works with any LLM, including Gemini.

6. **For hackathon**: Our custom GenUI is sufficient. OpenUI is the production upgrade path.
