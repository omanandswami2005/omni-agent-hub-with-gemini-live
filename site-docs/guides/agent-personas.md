# Agent Personas

Omni supports multiple AI personas — each with a unique system instruction, voice, model, and tool set.

## Built-in Personas

| Persona | Description | Capabilities |
|---|---|---|
| **Omni** (default) | General-purpose assistant | Search, tasks, image gen |
| **Coder** | Software development expert | Code execution, desktop, search |
| **Analyst** | Data analysis specialist | Code execution, search |
| **Researcher** | Deep research assistant | Search, tasks |
| **Pixel** (GenUI) | Visual data renderer | Code execution, GenUI schema |

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
