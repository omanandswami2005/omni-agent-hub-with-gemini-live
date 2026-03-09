# Gemini Live Agent Challenge — Compiled Brief

## Overview

Build a **next-generation AI Agent** using multimodal inputs/outputs that moves beyond text-in/text-out. Leverage Google's Live API + video/image generation to solve complex problems or create new user experiences.

---

## Mandatory Tech Stack

| Requirement | Detail |
|---|---|
| **AI Model** | Must use a Gemini model |
| **Agent Framework** | Google ADK (Agent Development Kit) |
| **Cloud** | At least one Google Cloud service |
| **Policy** | Must comply with [Google Cloud AUP](https://cloud.google.com/terms/aup) |

---

## Categories (Pick One)

### 1. Live Agents — Real-time Interaction (Audio/Vision)

- Agent users can **talk to naturally** and **interrupt** (barge-in)
- Examples: real-time translator, vision-enabled tutor that "sees" homework, voice customer support
- **Mandatory Tech:** Gemini Live API or ADK, hosted on Google Cloud

### 2. Creative Storyteller — Multimodal Storytelling with Interleaved Output

- Agent that **weaves text, images, audio, and video** in a single fluid output stream
- Leverage Gemini's **native interleaved output** for mixed-media responses
- Examples: interactive storybooks, marketing asset generator, educational explainers, social content creator
- **Mandatory Tech:** Gemini's interleaved/mixed output capabilities, hosted on Google Cloud

### 3. UI Navigator — Visual UI Understanding & Interaction

- Agent that **observes screen/browser**, interprets visual elements, and **performs actions** based on user intent
- With or without relying on APIs/DOM access
- Examples: universal web navigator, cross-application workflow automator, visual QA testing agent
- **Mandatory Tech:** Gemini multimodal for screenshot/screen recording interpretation → executable actions, hosted on Google Cloud

---

## Submission Checklist

### Required

| # | Item | Details |
|---|---|---|
| 1 | **Category Selection** | Pick one of the three categories |
| 2 | **Text Description** | Summary of features, functionality, technologies, data sources, findings & learnings |
| 3 | **Public Code Repository** | URL to public repo showing how it was built |
| 4 | **README with Spin-up Instructions** | Step-by-step setup guide (local or cloud deploy) proving reproducibility |
| 5 | **Proof of Google Cloud Deployment** | Either: (a) screen recording of app running on GCP (console logs/deployment view), OR (b) link to code file showing Google Cloud API usage |
| 6 | **Architecture Diagram** | Clear visual of system design (Gemini ↔ backend ↔ database ↔ frontend). Pro tip: add to file upload or image carousel |
| 7 | **Demo Video (≤ 4 min)** | Must show actual software working in real-time (no mockups), pitch the problem & solution, English or English subtitles, publicly visible on YouTube or Vimeo |

### Optional (Bonus Points)

| Bonus | Max Points | Details |
|---|---|---|
| **Published Content** | +0.6 | Blog/podcast/video on how the project was built with Google AI & Cloud. Must state it's for this hackathon. Use **#GeminiLiveAgentChallenge** on social media |
| **Automated Cloud Deployment** | +0.2 | Scripts or IaC tools in the public repo |
| **GDG Membership** | +0.2 | Link to public Google Developer Group profile |

---

## Judging Criteria

### Stage 1 — Pass/Fail Baseline

- Submission includes all requirements
- Reasonably addresses a challenge category
- Reasonably applies the mandatory tech

### Stage 2 — Scored (1–5 per criterion)

#### Innovation & Multimodal User Experience — 40%

- **"Beyond Text" Factor:** Breaks the text-box paradigm? Interaction is natural, immersive, superior to standard chat?
- **Category-Specific Execution:**
  - *Live Agents:* Handles interruptions (barge-in) naturally? Distinct persona/voice?
  - *Creative Storyteller:* Media interleaved seamlessly into coherent narrative?
  - *UI Navigator:* Visual precision (understanding screen context) vs. blind clicking?
- **Fluidity:** "Live" and context-aware, or disjointed and turn-based?

#### Technical Implementation & Agent Architecture — 30%

- **Google Cloud Native:** Effective use of Google GenAI SDK/ADK? Robust hosting (Cloud Run, Vertex AI, Firestore)?
- **System Design:** Sound agent logic? Handles errors, API timeouts, edge cases gracefully?
- **Robustness:** Avoids hallucinations? Evidence of grounding?

#### Demo & Presentation — 30%

- **The Story:** Video clearly defines problem and solution?
- **The Proof:** Architecture diagram clear? Visual proof of Cloud deployment?
- **The "Live" Factor:** Video shows actual working software?

### Stage 3 — Bonus Contributions (added to Stage 2 score)

- Published content: up to +0.6
- Automated deployment: up to +0.2
- GDG membership: up to +0.2
- **Maximum possible final score: 6**

### Tiebreakers

1. Compare scores on each criterion in listed order
2. If still tied, judges vote

---

## Prizes — $80,000 Total

| Prize | Cash | Cloud Credits | Extras |
|---|---|---|---|
| **Grand Prize** (1 winner, best across all categories) | $25,000 | $3,000 | Virtual coffee w/ Google, social promo, 2× Cloud Next 2026 tickets ($2,299 ea), 2× travel stipends ($3,000 ea), opportunity to demo at Cloud Next 2026 |
| **Best Live Agent** (1 winner) | $10,000 | $1,000 | Virtual coffee, social promo, 2× Cloud Next 2026 tickets |
| **Best Creative Storyteller** (1 winner) | $10,000 | $1,000 | Virtual coffee, social promo, 2× Cloud Next 2026 tickets |
| **Best UI Navigator** (1 winner) | $10,000 | $1,000 | Virtual coffee, social promo, 2× Cloud Next 2026 tickets |
| **Best Multimodal Integration & UX** (1 winner) | $5,000 | $500 | — |
| **Best Technical Execution & Agent Architecture** (1 winner) | $5,000 | $500 | — |
| **Best Innovation & Thought Leadership** (1 winner) | $5,000 | $500 | — |
| **Honorable Mentions** (5 winners) | $2,000 each | $500 each | — |

> If a project wins both a category prize and a subcategory prize, the subcategory prize goes to the next highest-scoring project.

---

## Key Dates

| Milestone | Date |
|---|---|
| **Submission Deadline** | Before March 17, 2026 |
| **Judging Period** | March 17 – April 3, 2026 |
| **Google Cloud Next 2026** | April 22–24, 2026 |

---

## Rules Snapshot

- **Team:** Individual, team, or organization. All members must be eligible and listed on Devpost.
- **New Projects Only:** Created during the contest period. No modifications of existing work.
- **Third-Party Integrations:** Must be authorized; must disclose in submission description.
- **Functionality:** Must install and run consistently as depicted in the demo video.
- **Testing:** Project must be available free of charge for judging until Judging Period ends.
- **Draft Submissions:** Can save drafts on Devpost before deadline; no changes after Submission Period.

---

## Winning Strategy Summary

To maximize score (out of 6):

1. **Nail the multimodal experience (40%)** — make it feel natural, immersive, "beyond text"
2. **Solid technical execution (30%)** — proper ADK usage, robust Cloud hosting, error handling, grounding
3. **Compelling demo video (30%)** — clear problem/solution story, show real working software, include architecture proof
4. **Grab all bonus points (+1.0)** — publish content (+0.6), automate deployment (+0.2), join GDG (+0.2)
