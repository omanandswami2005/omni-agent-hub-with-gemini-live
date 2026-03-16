# Omni Agent Hub — Blog Posts & Media Assets

## Overview
This folder contains all the technical blog posts, image generation prompts, Mermaid diagrams, diagram descriptions, and social media copy required for the Omni Agent Hub submission to the Gemini Live Agent Challenge Hackathon on Devpost.

## Blog Posts
- **Blog #1: Building Omni** (`blog-1-building-omni.md`) — Primary hackathon submission blog detailing the architecture, plugins, and cloud deployment of the multi-client AI hub. (2500-4000 words)
- **Blog #2: Cross-Client Deep Dive** (`blog-2-cross-client-deep-dive.md`) — Companion technical deep-dive focusing on the Event Bus, session-first design, and the cross-device device controller. (2000-3000 words)

## Visual Assets
- **AI Image Generation Prompts** (`image-prompts.md`) — 14 detailed prompts for generating all required assets using DALL-E, Midjourney, or Gemini Imagen.
- **Mermaid Diagrams** (`diagrams/mermaid-diagrams.md`) — 10 renderable Mermaid.js diagrams illustrating the system architecture, state machines, and data flow.
- **Diagram Descriptions** (`diagrams/diagram-descriptions.md`) — Manual recreation guides for all 14 images and 10 diagrams using tools like draw.io or Excalidraw.

## Social Media
- **Social Media Posts** (`social-media-posts.md`) — Ready-to-post promotional content for Twitter/X, LinkedIn, Reddit, Dev.to, and the Devpost submission description.

## Live URLs
- **Live Demo:** https://gemini-live-hackathon-2026.web.app
- **Backend API:** https://omni-backend-fcapusldtq-uc.a.run.app
- **GitHub Pages:** https://omanandswami2005.github.io/omni-agent-hub-with-gemini-live

---

## Publishing Checklist

### Pre-Publishing
- [x] Blog #1 reviewed for accuracy (all code references verified against repo).
- [x] Blog #2 reviewed for accuracy.
- [ ] Generate all 14 images using prompts from `image-prompts.md`.
- [ ] Render all 10 Mermaid diagrams at [https://mermaid.live](https://mermaid.live) and screenshot them.
- [ ] Replace all `> 📸 [IMAGE]` placeholders in blogs with actual images.

### Publishing to Medium
- [ ] Create Medium account (if needed).
- [ ] Copy Blog #1 content into Medium editor.
- [ ] Upload all images at marked placeholder locations.
- [ ] Set title and subtitle.
- [ ] Add 5 tags: Google Gemini, AI Agents, Hackathon, Google Cloud, Artificial Intelligence.
- [ ] Set cover/preview image (use `hero-banner`).
- [ ] Verify all 3 live URLs are clickable in the post.
- [ ] Verify hackathon disclaimer appears at BOTH top and bottom.
- [ ] Preview on desktop AND mobile.
- [ ] Click Publish.
- [ ] Repeat for Blog #2.

### Post-Publishing
- [ ] Copy the Medium URL.
- [ ] Post on Twitter/X (pick from 3 versions in `social-media-posts.md`).
- [ ] Post on LinkedIn (pick from 2 versions).
- [ ] Optionally post on Reddit.
- [ ] Optionally cross-post to Dev.to.
- [ ] Add blog URL to Devpost submission.
- [ ] Verify `#GeminiLiveAgentChallenge` hashtag is on all social posts.

---

## Image Placement Quick Reference

**Blog #1 Images (in order of appearance):**
1. `hero-banner` — After title, before "The Problem" section
2. `architecture-diagram` — Start of "Architecture" section
3. `agent-routing-flow` — After Layer 3 description
4. `voice-pipeline-diagram` — Start of "Voice Pipeline" section
5. `plugin-architecture` — Start of "Plugin Ecosystem" section
6. `genui-showcase` — In "Frontend & GenUI" section
7. `cloud-architecture` — Start of "Google Cloud Stack" section
8. `event-bus-diagram` — In "Cross-Client Event Bus" section
9. `multi-client-showcase` — In "Supported Clients" section

**Blog #2 Images (in order of appearance):**
1. `session-first-diagram` — In "Session-First Architecture" section
2. `event-bus-flow` — In "Event Bus Deep Dive" section
3. `cross-device-orchestration` — In "Cross-Device Orchestration" section
4. `all-clients-grid` — In "Client Deep Dives" section
5. `mic-floor-state-machine` — In "Mic Floor Management" section
