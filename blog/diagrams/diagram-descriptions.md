Diagram: hero-banner
Best Tool: Excalidraw / Figma
Layout: Background image with overlaid text
Canvas Size: 1200x630px
Components:
- Background image of a futuristic tech scene with a smartphone, laptop, smart glasses, and terminal connected by glowing lines.
- Text: "Omni Agent Hub" - White bold text centered - Overlaid on background

Diagram: architecture-diagram
Best Tool: draw.io / Figma
Layout: Top-to-bottom hierarchy
Canvas Size: 1200x800px
Components:
- Box: Root Router - Purple - Top center
- Box: Persona Pool - Blue - Middle left
- Box: TaskArchitect - Blue - Middle center
- Box: Device Controller - Blue - Middle right
- Box: Gemini Live API - Teal - Bottom left
- Box: Firestore - Orange - Bottom center-left
- Box: Cloud Run - Teal - Bottom center
- Box: MCP Servers - Gray - Bottom center-right
- Box: E2B - Gray - Bottom right
- Arrow: Root Router → Persona Pool
- Arrow: Root Router → TaskArchitect
- Arrow: Root Router → Device Controller
- Arrows connecting middle layer to bottom layer external services
Color Scheme:
- Agent/AI elements: Purple (#8B5CF6)
- Client devices: Blue (#3B82F6)
- Google Cloud services: Teal (#14B8A6)
- Connections/Arrows: White or light gray

Diagram: agent-routing-flow
Best Tool: draw.io / Canva
Layout: Top-to-bottom decision tree
Canvas Size: 1200x800px
Components:
- Oval: User Message - Blue - Top
- Diamond: Intent Classification - Purple - Below User Message
- Box: Simple (Direct Response) - Gray - Below left
- Box: Specialized (Persona) - Gray - Below center-left
- Box: Complex (TaskArchitect) - Gray - Below center-right
- Box: Device (Device Controller) - Gray - Below right
- Arrow: User Message → Intent Classification
- Arrows splitting from Diamond to each Box

Diagram: voice-pipeline-diagram
Best Tool: Excalidraw / Figma
Layout: Left-to-right parallel flows
Canvas Size: 1200x600px
Components:
- Box: Mic Icon - Blue - Left top
- Box: AudioWorklet - Gray - Middle left top
- Box: Server / Gemini - Purple - Center top
- Box: Jitter Buffer - Gray - Middle right top
- Box: Speaker Icon - Blue - Right top
- Box: Camera Icon - Blue - Left bottom
- Box: Vision Stream - Gray - Center bottom
- Arrows: Flowing left to right indicating PCM16 in, PCM24 out.

Diagram: plugin-architecture
Best Tool: draw.io
Layout: Circular / Hub-and-spoke
Canvas Size: 1000x700px
Components:
- Circle: Unified Plugin Registry - Purple - Center
- Box: MCP Servers - Gray - Left top
- Box: Native Python - Gray - Left middle
- Box: E2B Sandbox - Gray - Left bottom
- Box: Coder Persona - Blue - Right top
- Box: Researcher Persona - Blue - Right middle
- Box: Analyst Persona - Blue - Right bottom
- Arrows connecting outer boxes to center circle

Diagram: genui-showcase
Best Tool: Figma / Canva
Layout: 2x2 Grid Mockup
Canvas Size: 1200x800px
Components:
- A dark background panel representing a UI dashboard.
- Box: Bar Chart Image - Top Left
- Box: Code Block Syntax - Top Right
- Box: Data Table UI - Bottom Left
- Box: Map View UI - Bottom Right

Diagram: cloud-architecture
Best Tool: draw.io / PowerPoint
Layout: Structured Cloud Architecture
Canvas Size: 1200x800px
Components:
- Box: Cloud Run - Teal - Top center
- Box: Firestore - Orange - Middle left
- Box: Firebase Auth - Yellow - Middle center
- Box: Vertex AI - Purple - Middle right
- Box: Secret Manager - Gray - Bottom left
- Box: Cloud Storage - Blue - Bottom right
- Arrows indicating bi-directional data flow from Cloud Run to others.

Diagram: event-bus-diagram
Best Tool: Excalidraw / draw.io
Layout: Left-to-right fan-out
Canvas Size: 1000x600px
Components:
- Box: Mobile Device - Blue - Left
- Circle: Event Bus Hub - Purple - Center
- Box: Web Dashboard - Blue - Right top
- Box: Desktop Client - Blue - Right middle
- Box: Smart Glasses - Blue - Right bottom
- Arrows fanning out from center to right.

Diagram: event-bus-flow
Best Tool: draw.io (Sequence Diagram mode)
Layout: Vertical Lifelines
Canvas Size: 1200x900px
Components:
- Lifelines for: User, Mobile, Hub, Gemini, Event Bus, Web, Desktop
- Arrows showing horizontal message passing chronologically down the page.

Diagram: session-first-diagram
Best Tool: Canva
Layout: Side-by-side comparison
Canvas Size: 1200x600px
Components:
- Left Column: "Traditional" - 3 isolated devices each connected to their own small cloud icon.
- Right Column: "Omni" - 3 devices all connected via lines to one single large glowing brain/cloud icon in the center.

Diagram: cross-device-orchestration
Best Tool: draw.io
Layout: Circular process flow
Canvas Size: 1200x800px
Components:
- 7 numbered circles around the edge connected by arrows in a clockwise direction.
- Text labels for each step (Phone voice, Hub routing, etc.) next to the circles.

Diagram: all-clients-grid
Best Tool: Figma / Canva
Layout: 2x3 Grid
Canvas Size: 1200x600px
Components:
- 6 equal-sized boxes containing distinct icons (Browser, Phone, Monitor, Glasses, Terminal, Puzzle Piece).
- Text labels below each icon indicating name and connection type (WebSocket).

Diagram: mic-floor-state-machine
Best Tool: Excalidraw / draw.io
Layout: Triangular state layout
Canvas Size: 800x500px
Components:
- Circle: IDLE - Green - Top
- Circle: STREAMING - Blue - Bottom Left
- Circle: LISTEN_ONLY - Gray - Bottom Right
- Arrows showing transitions with labels (acquire_mic, release_mic).

Diagram: multi-client-showcase
Best Tool: 3D modeling or advanced Figma mockups
Layout: Perspective/Isometric
Canvas Size: 1200x800px
Components:
- Phone mockup showing voice UI
- Laptop mockup showing GenUI chart
- Monitor mockup showing dashboard
- Glasses mockup showing AR UI
- Connecting glowing lines between them
