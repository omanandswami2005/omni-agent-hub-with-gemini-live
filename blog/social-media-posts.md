# Social Media Posts for Omni Agent Hub

## Twitter/X Posts

### Version 1 — Technical Focus
Just shipped Omni for the #GeminiLiveAgentChallenge! 🚀 It's a multi-client AI hub using Google Gemini Live API. Speak to one brain from Web, Desktop, Mobile & Smart Glasses simultaneously. Features: pub/sub event bus, dynamic GenUI, and cross-device routing. Check it out: [BLOG_LINK]

### Version 2 — Demo/Visual Focus
*(Attach Image: multi-client-showcase or video demo)*
Why have a separate AI for every device? Meet Omni. 🧠 I built a unified agent platform where you can talk to Gemini on your phone and watch the UI render instantly on your laptop. Built for the #GeminiLiveAgentChallenge! Dive into the architecture here: [BLOG_LINK]

### Version 3 — Thread Format
**Tweet 1:** Every AI assistant today is an island. You can't switch devices mid-thought. For the #GeminiLiveAgentChallenge, I built Omni: a unified agent hub that lets you speak anywhere and act everywhere. 🧵👇
**Tweet 2:** Omni isn't just a web app. It connects a React dashboard, a Python desktop client, a mobile PWA, and even ESP32 smart glasses to ONE central Gemini Live session.
**Tweet 3:** The tech stack: FastAPI, Google Cloud Run, Firestore, Firebase Auth, and the Gemini Live API with WebSockets handling bi-directional binary audio and JSON events.
**Tweet 4:** The coolest part? Cross-device orchestration. You can tell your phone "take a screenshot on my desktop", and the backend routes the command to your PC, captures the screen, and sends it to Gemini for analysis in real-time.
**Tweet 5:** Check out the live demo and full technical deep-dive on how I built the event bus and dynamic GenUI here: [BLOG_LINK] #GeminiLiveAgentChallenge #GoogleCloud #AI

---

## LinkedIn Posts

### Version 1 — Professional/Technical
I'm excited to share my submission for the #GeminiLiveAgentChallenge: Omni Agent Hub.

Most AI assistants are siloed to a single device. Omni changes that by introducing a "Session-First" architecture. Powered by the Google Gemini Live API, Cloud Run, and FastAPI, Omni allows you to maintain a single continuous conversation across your web browser, desktop, mobile phone, and even custom smart glasses.

Key technical highlights include:
🔹 Bi-directional WebSocket streaming for real-time PCM audio.
🔹 A custom Fan-out Event Bus to synchronize GenUI components across all connected clients.
🔹 A 3-layer agent architecture (Root Router, Persona Pool, TaskArchitect) capable of dynamic tool execution using MCP and E2B sandboxes.

I wrote a comprehensive deep-dive into the architecture and how to handle cross-device synchronization in real-time. Read it here: [BLOG_LINK]

#GoogleCloud #AI #Hackathon #GeminiAPI #BuildWithAI #SoftwareEngineering

### Version 2 — Personal Journey/Story
Building for the #GeminiLiveAgentChallenge pushed me to rethink how we interact with AI.

I was frustrated that I couldn't start an AI task on my phone while walking, and then seamlessly see the generated code or charts when I sat down at my laptop. That frustration led to Omni.

Over the past few weeks, I built a unified AI brain that connects edge devices (from a React dashboard to Python desktop apps and ESP32 smart glasses) via a central real-time hub using Google's Gemini Live API. Figuring out the mic-floor state management and the zero-latency event broadcast was incredibly challenging, but seeing a voice command on my phone instantly execute a Python script on my desktop made it all worth it.

If you are interested in multi-modal AI and real-time distributed systems, I documented the entire build process and architecture in my latest blog post: [BLOG_LINK]

#GeminiLiveAgentChallenge #GoogleCloud #AI #Hackathon #GeminiAPI #BuildWithAI

---

## Reddit Posts

### r/artificial
**Title:** I built an open-source AI hub that spans across Mobile, Web, Desktop, and Smart Glasses using Gemini Live.
**Body:**
Hey r/artificial, I wanted to share a project I just finished for a hackathon: Omni Agent Hub.

Instead of having a separate ChatGPT/Claude instance on every device, Omni creates one persistent session. You can speak to it on your phone, and it will render UI components (GenUI) on your desktop monitor simultaneously using a real-time event bus. It can even execute cross-device commands (like telling your phone to take a screenshot on your PC).

It uses the Gemini Live API for sub-second voice interactions and a custom FastAPI/WebSocket backend to orchestrate the devices.

I wrote a detailed technical breakdown of the architecture here: [BLOG_LINK]
Live Demo: https://gemini-live-hackathon-2026.web.app
GitHub: https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live

### r/MachineLearning
**Title:** Omni: A 3-Layer Multi-Client Agent Architecture using Gemini Live API and Dynamic Tool Calling (MCP/E2B)
**Body:**
For the Gemini Live Agent Challenge, I developed a platform to solve the multi-device fragmentation problem in LLM clients.

Omni implements a Layered Agent Architecture:
1. **Layer 0 (Root Router):** Fast intent classification.
2. **Layer 1 (Persona Pool):** Specialized agents equipped with specific MCP/Native tools.
3. **Layer 2 (Task Architect):** Generates execution DAGs for complex tasks.
4. **Layer 3 (Device Controller):** Manages physical cross-device execution (e.g., executing scripts on a connected desktop node).

All of this operates over a single unified WebSocket connection pushing binary PCM audio to the Gemini Live API while broadcasting state deltas via a custom Pub/Sub event bus to multiple connected frontend clients (React, PyQt6, ESP32).

Full architectural write-up: [BLOG_LINK]
Backend Repo: https://omni-backend-fcapusldtq-uc.a.run.app

### r/GoogleCloud
**Title:** Built a Real-Time Voice AI Platform scaling with Cloud Run, Firestore, and Vertex AI for the Gemini Hackathon
**Body:**
Just deployed Omni, a multi-client agent hub built entirely on GCP.

The architecture leverages:
- **Vertex AI:** Utilizing the new Gemini Live API for bi-directional streaming.
- **Cloud Run:** Hosting the FastAPI WebSocket server. It scales beautifully for long-lived concurrent connections.
- **Firestore:** Managing real-time session states, memories, and task execution graphs.
- **Firebase Auth:** Handling secure JWTs across Web, Desktop, and Mobile clients.

Handling binary audio streams while simultaneously syncing JSON UI events to multiple devices required some interesting architectural patterns (specifically around event fan-out and connection deduplication).

I did a full technical deep dive on the cloud architecture here: [BLOG_LINK]

---

## Dev.to Cross-Post Intro

**Intro to prepend to the Dev.to post:**
*This post was originally written for the Gemini Live Agent Challenge Hackathon on Devpost. In this deep dive, I explore how to break AI assistants out of the single-device silo by building a real-time, multi-modal backend using Python, WebSockets, and the Google Gemini Live API. Let's dig into the code!*

*(Suggested tags: #python #react #ai #googlecloud)*

---

## Devpost Submission Description

**Omni Agent Hub: Speak Anywhere, Act Everywhere.**

**The Problem:** Today's AI assistants are isolated islands. Your phone AI doesn't know what your desktop AI is doing. You can't switch devices mid-thought, and you certainly can't tell your phone to execute a script on your laptop.

**The Solution:** Omni is a unified, session-first AI platform. Powered by the groundbreaking **Google Gemini Live API** and the Google ADK, Omni provides a single intelligent brain that connects to all your devices simultaneously.

**Key Features:**
- **Cross-Client Orchestration:** Give a voice command to your AR Smart Glasses and watch the resulting data chart render instantly on your Web Dashboard.
- **Real-Time Voice & Vision:** Sub-second bi-directional audio streaming and continuous camera frame analysis using Gemini Live.
- **Dynamic GenUI:** The AI doesn't just return text; it streams structured JSON to generate interactive charts, code blocks, and maps in real-time.
- **Extensible Plugin Ecosystem:** Support for MCP servers, native Python execution, and secure E2B cloud sandboxing.

**How it's Built:**
The backend is a high-performance Python/FastAPI service deployed on **Google Cloud Run**, utilizing **Firestore** for state and **Firebase Auth** for security. A custom fan-out Event Bus ensures zero-latency synchronization across the React Web App, Python Desktop Client, Mobile PWA, and hardware edge devices.

**Links:**
Live Demo: https://gemini-live-hackathon-2026.web.app
Full Technical Architecture Blog: [BLOG_LINK]
