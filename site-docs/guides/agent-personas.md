# Agent Personas

Omni supports multiple AI personas — each with a unique system instruction, voice, model, and tool set. Each persona is wrapped as an **AgentTool** on the root agent, running via `Runner.run_async()` with the `generateContent` API (not the Live API).

## Built-in Personas

| Persona | Description | Capabilities | Model |
|---|---|---|---|
| **Claire** (assistant) | General-purpose assistant | Search, tasks, image gen | `gemini-2.5-flash` |
| **Dev** (coder) | Software development expert | Code execution, desktop, search | `gemini-2.5-flash` |
| **Nova** (analyst) | Data analysis specialist | Code execution, search | `gemini-2.5-flash` |
| **Sage** (researcher) | Deep research assistant | Search, tasks | `gemini-2.5-flash` |
| **Muse** (creative) | Creative collaborator | Image generation, media | `gemini-2.5-flash` |
| **Pixel** (genui) | Visual data renderer | Code execution, GenUI schema | `gemini-2.5-flash-lite` |

## Creating a Custom Persona

### Via REST API

```bash
POST /personas
{
  "name": "My Persona",
  "system_instruction": "You are a helpful marketing assistant...",
  "voice": "Kore",
  "model_override": null,
  "capabilities": ["search", "task"]
}
```

### Via Dashboard

1. Open the Persona panel in the sidebar
2. Click **+ New Persona**
3. Fill in name, instruction, voice, and capabilities
4. Click **Save**

## Capability Tags

Each persona declares which tool categories it can use:

| Tag | Tools Included |
|---|---|
| `search` | Google Search |
| `code_execution` | E2B code interpreter |
| `desktop` | E2B virtual desktop |
| `image_gen` | Imagen image generation |
| `task` | Planned tasks, scheduling |
| `cross_client` | Cross-device actions |
| `genui` | GenUI schema lookup |
| `wildcard` | MCP plugins |
