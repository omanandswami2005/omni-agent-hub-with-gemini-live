---
### Diagram: System Architecture
**Used In:** Blog #1
**Description:** Full system showing all 3 agent layers, all client types, all cloud services, plugin registry, event bus.
**Render at:** https://mermaid.live

```mermaid
graph TD
    subgraph Clients["Edge Clients (WebSocket)"]
        Web["Web Dashboard"]
        Mobile["Mobile PWA"]
        Desktop["Desktop Client"]
        Glasses["Smart Glasses (UDP Bridge)"]
        CLI["Terminal CLI"]
        Ext["Chrome Extension"]
    end

    subgraph Agent_Brain["Omni Agent Hub (Python/FastAPI)"]
        Router["Layer 0: Root Router"]

        subgraph Layer1["Layer 1: Persona Pool"]
            Coder["Coder Agent"]
            Researcher["Researcher Agent"]
            Analyst["Analyst Agent"]
        end

        TaskArch["Layer 2: TaskArchitect"]
        DeviceCtrl["Layer 3: Device Controller"]

        EventBus["Event Bus (Fan-out)"]
        PluginReg["Plugin Registry"]
    end

    subgraph Cloud["Google Cloud Stack"]
        CloudRun["Cloud Run (Compute)"]
        Firestore["Firestore (Data/Memory)"]
        Vertex["Vertex AI / Gemini Live"]
        Auth["Firebase Auth"]
        SecretMgr["Secret Manager"]
    end

    subgraph External["External Tools & execution"]
        MCPServers["MCP Servers"]
        E2B["E2B Sandboxes"]
        Native["Native Plugins"]
    end

    Web -->|Auth & WSS| Router
    Mobile -->|Auth & WSS| Router
    Desktop -->|Auth & WSS| Router
    Glasses -->|Auth & WSS| Router
    CLI -->|Auth & WSS| Router
    Ext -->|Auth & WSS| Router

    Router -->|Simple intent| Layer1
    Router -->|Complex multi-step| TaskArch
    Router -->|Hardware action| DeviceCtrl

    Layer1 <--> PluginReg
    TaskArch <--> PluginReg

    PluginReg --> MCPServers
    PluginReg --> E2B
    PluginReg --> Native

    Router <--> Vertex
    Layer1 <--> Vertex
    TaskArch <--> Vertex
    DeviceCtrl <--> Vertex

    Agent_Brain --> EventBus
    EventBus --> Clients

    Agent_Brain <--> Firestore
    Agent_Brain <--> SecretMgr
    Clients --> Auth
    Agent_Brain --> CloudRun
```

---
### Diagram: Agent Routing Flow
**Used In:** Blog #1
**Description:** Decision tree for message classification. Start with user message, classify intent, route to appropriate layer.
**Render at:** https://mermaid.live

```mermaid
flowchart TD
    Start([User Message]) --> Classify{Intent Classification}

    Classify -->|Direct Response| Simple[Layer 0: Root Agent]
    Classify -->|Specialized Topic| Persona[Layer 1: Persona Pool]
    Classify -->|Complex Multi-step| Task[Layer 2: TaskArchitect]
    Classify -->|Hardware/Client Action| Device[Layer 3: Device Controller]

    Simple -.->|"What time is it?"| End1([Quick Reply])
    Persona -.->|"Write a Python script"| End2([Coder Agent])
    Task -.->|"Research X, summarize Y, email Z"| End3([Pipeline Created])
    Device -.->|"Take a screenshot"| End4([Cross-Client Command])
```

---
### Diagram: Voice Pipeline
**Used In:** Blog #1
**Description:** Left-to-right audio flow from microphone to speaker. Include both upstream and downstream paths.
**Render at:** https://mermaid.live

```mermaid
graph LR
    subgraph Client["Edge Client"]
        Mic((Microphone))
        AudioWork[AudioWorklet]
        Buffer[Jitter Buffer]
        Speaker((Speaker))
        Cam((Camera))
    end

    subgraph Transport["WebSocket"]
        UpWS[Binary Upstream]
        DownWS[Binary Downstream]
        VisWS[Vision Frames]
    end

    subgraph Backend["Omni Hub + Gemini"]
        Server[FastAPI ws_live]
        Gemini[Gemini Live API]
    end

    Mic -->|Raw PCM| AudioWork
    AudioWork -->|PCM16 16kHz| UpWS
    UpWS --> Server

    Cam -->|JPEG Snapshots| VisWS
    VisWS --> Server

    Server <-->|Bidi Stream| Gemini

    Server -->|PCM24 24kHz| DownWS
    DownWS --> Buffer
    Buffer -->|Playback| Speaker
```

---
### Diagram: Event Bus Fan-Out
**Used In:** Blog #1
**Description:** Sequence showing a Mobile user speaking, events processing, and fanning out to multiple devices.
**Render at:** https://mermaid.live

```mermaid
sequenceDiagram
    participant User
    participant Mobile as Mobile Client
    participant Hub as Omni Hub
    participant Gemini as Gemini Live
    participant Bus as Event Bus
    participant Web as Web Dashboard
    participant Desk as Desktop Client

    User->>Mobile: "Show me a chart of sales"
    Mobile->>Hub: Audio Stream (WebSocket)
    Hub->>Gemini: Forward Audio
    Gemini-->>Hub: Structured JSON + Audio Response
    Hub-->>Mobile: Audio Playback

    Hub->>Bus: publish(user_id, GenUI_Event)

    Bus-->>Mobile: Event (origin_conn match, ignore)
    Bus-->>Web: Event (render GenUI Chart)
    Bus-->>Desk: Event (show notification)

    Note over Web: Renders interactive chart
    Note over Desk: "New chart generated"
```

---
### Diagram: Cross-Device Orchestration
**Used In:** Blog #2
**Description:** Detailed sequence for "Take a screenshot on my desktop" scenario from a phone.
**Render at:** https://mermaid.live

```mermaid
sequenceDiagram
    participant User
    participant Phone as Mobile Client
    participant Hub as Device Controller
    participant Desk as Desktop Client
    participant Gemini as Gemini Live

    User->>Phone: "Take a screenshot on my desktop"
    Phone->>Hub: Voice command
    Hub->>Gemini: Intent classification
    Gemini-->>Hub: Use tool: send_to_desktop(action="screenshot")

    Hub->>Desk: WebSocket Command (action="screenshot")
    Note over Desk: PyAutoGUI / mss executes
    Desk-->>Hub: Screenshot Image Data

    Hub->>Gemini: Upload Image Context
    Gemini-->>Hub: "Screenshot captured. Here's what I see..."
    Hub-->>Phone: Audio Response
```

---
### Diagram: Mic Floor State Machine
**Used In:** Blog #2
**Description:** Three states (IDLE, STREAMING, LISTEN_ONLY) with all transitions and trigger labels.
**Render at:** https://mermaid.live

```mermaid
stateDiagram-v2
    [*] --> IDLE

    IDLE --> STREAMING : acquire_mic (Granted)
    IDLE --> LISTEN_ONLY : Another device acquired floor

    STREAMING --> IDLE : release_mic (Finished speaking)
    STREAMING --> IDLE : Auto-timeout (Inactivity)

    LISTEN_ONLY --> IDLE : Floor released by other device

    LISTEN_ONLY --> LISTEN_ONLY : Ignore local mic input
```

---
### Diagram: Plugin System
**Used In:** Blog #1
**Description:** Show MCP Servers + Native Plugins + E2B flowing into Plugin Registry, then Tool Registry mapping to Personas.
**Render at:** https://mermaid.live

```mermaid
graph TD
    subgraph Sources["Plugin Sources"]
        MCP["MCP Servers (stdio/HTTP)"]
        Native["Native Python Plugins"]
        E2B["E2B Sandboxes"]
    end

    Reg["Plugin Registry"]
    Tools["Tool Capability Mapper"]

    MCP --> Reg
    Native --> Reg
    E2B --> Reg

    Reg --> Tools

    subgraph Personas["Persona Pool"]
        Coder["Coder (needs execution)"]
        Research["Researcher (needs search)"]
        Analyst["Analyst (needs data)"]
    end

    Tools -->|Maps 'execute'| Coder
    Tools -->|Maps 'search'| Research
    Tools -->|Maps 'query'| Analyst
```

---
### Diagram: Data Model
**Used In:** Blog #1
**Description:** Firestore collections: sessions, memories, tasks, plugin_enabled_state showing relationships.
**Render at:** https://mermaid.live

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : owns
    USERS ||--o{ MEMORIES : has
    USERS ||--o{ PLUGINS : configures
    SESSIONS ||--o{ TASKS : contains

    USERS {
        string uid PK
        string email
    }

    SESSIONS {
        string session_id PK
        string title
        timestamp created_at
    }

    MEMORIES {
        string memory_id PK
        string content
        string source_session
    }

    TASKS {
        string task_id PK
        string session_id FK
        string status
        json blueprint
    }

    PLUGINS {
        string user_id FK
        string plugin_id
        boolean enabled
    }
```

---
### Diagram: Deployment Architecture
**Used In:** Blog #1
**Description:** Google Cloud services architecture showing data flow.
**Render at:** https://mermaid.live

```mermaid
graph TD
    User((User Devices))

    subgraph Google_Cloud["Google Cloud Platform"]
        LoadBal["Cloud Load Balancing"]
        Run["Cloud Run (FastAPI)"]

        Auth["Firebase Auth"]
        Firestore[(Firestore)]
        Storage[(Cloud Storage)]
        Secrets["Secret Manager"]

        Vertex["Vertex AI / Gemini Live"]
    end

    User -->|HTTPS/WSS| LoadBal
    User -->|Login| Auth

    LoadBal --> Run

    Run <-->|Validate JWT| Auth
    Run <-->|Read/Write State| Firestore
    Run <-->|Store Images| Storage
    Run <-->|Get API Keys| Secrets
    Run <-->|Bidi Audio & Inference| Vertex
```

---
### Diagram: GenUI Flow
**Used In:** Blog #1
**Description:** From user query to rendered React component via Gemini JSON structure.
**Render at:** https://mermaid.live

```mermaid
graph LR
    User([User Query]) --> Gemini[Gemini Generation]
    Gemini -->|Structured JSON| Hub[Backend Hub]
    Hub -->|EventBus WSS| React[React Dashboard]
    React --> State[Zustand Store]
    State --> Render[GenUIRenderer]

    Render -->|type: chart| Chart[BarChart Component]
    Render -->|type: code| Code[CodeBlock Component]
    Render -->|type: map| Map[MapView Component]
```
