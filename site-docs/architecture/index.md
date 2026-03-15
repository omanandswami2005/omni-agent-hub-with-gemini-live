# Architecture Overview

Omni follows a **hub-and-spoke architecture** where a single FastAPI backend acts as the central brain, connecting multiple client types to Google's Gemini Live API through the Google ADK agent framework.

## High-Level Architecture

```mermaid
graph LR
    subgraph Clients
        WEB[Web Dashboard<br/>React 19]
        DESK[Desktop Client<br/>PyQt6]
        EXT[Chrome Extension]
        GLASS[Smart Glasses<br/>ESP32]
        CLI_C[CLI Client]
    end

    subgraph Backend["Backend (Cloud Run)"]
        API[FastAPI]
        ADK[Google ADK<br/>Agent Runtime]
        MCP[MCP Plugin<br/>Registry]
        TOOLS[Tool Registry<br/>T1+T2+T3]
    end

    subgraph Services
        E2B_CODE[E2B Code<br/>Sandbox]
        E2B_DESK[E2B Desktop<br/>Sandbox]
        FIRE[Firebase Auth<br/>+ Firestore]
    end

    subgraph Google["Google Cloud"]
        GEMINI[Gemini Live API]
        VERTEX[Vertex AI]
    end

    WEB & DESK & EXT & GLASS & CLI_C <-->|WebSocket| API
    API --> ADK
    ADK <-->|Bidi Streaming| GEMINI
    ADK --> MCP
    ADK --> TOOLS
    API --> E2B_CODE & E2B_DESK
    API --> FIRE
    ADK --> VERTEX
```

## Tool Tiers

Omni uses a three-tier tool system:

| Tier | Name | Description | Examples |
|---|---|---|---|
| **T1** | Built-in | Compiled into the agent at startup | Search, code exec, image gen, desktop tools |
| **T2** | MCP Plugins | Loaded from MCP servers (STDIO/HTTP/OAuth) | Brave Search, Google Maps, Zapier |
| **T3** | Client Tools | Provided by connected clients (reverse-RPC) | Screen capture, mouse/keyboard, file access |

## Agent System

Agents are built dynamically based on **persona** configuration:

```mermaid
flowchart TD
    PERSONA[Persona Config] --> FACTORY[Agent Factory]
    FACTORY --> T1[T1 Built-in Tools]
    FACTORY --> T2[T2 MCP Tools]
    FACTORY --> T3[T3 Client Tools]
    FACTORY --> AGENT[LlmAgent]
    AGENT --> LIVE[Gemini Live API<br/>Bidi Streaming]
```

## Component Details

- [Backend Architecture](backend.md)
- [Dashboard Architecture](dashboard.md)
- [Desktop Client Architecture](desktop-client.md)
- [Chrome Extension Architecture](chrome-extension.md)
