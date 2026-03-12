# Track 2: MCP Server Developer Guide

> **Scope**: Create new MCP (Model Context Protocol) tool servers that plug into Omni Hub.
> **Language**: Python (recommended) — any language with MCP SDK works
> **Time to first MCP server**: ~20 minutes
> **Prerequisites**: Python, understand what an MCP tool is

---

## What Is an MCP Server?

An MCP server exposes **tools** (functions) over a standardised protocol so that any MCP-compatible host can discover and call them. Think of it like a microservice that speaks a common tool-calling contract.

Omni Hub consumes MCP servers through its plugin system:
- **mcp_stdio**: The backend spawns the MCP server as a subprocess (`stdin`/`stdout` communication)
- **mcp_http**: The backend connects to a remote MCP server over HTTP/SSE

---

## Quick Start — Build an MCP Server in 5 Minutes

### Step 1: Install FastMCP

```bash
pip install mcp
```

### Step 2: Create your server file

```python
# my_tools_server.py
from mcp.server import FastMCP

mcp = FastMCP("my-tools")


@mcp.tool()
def greet(name: str) -> str:
    """Say hello to someone by name."""
    return f"Hello, {name}! Welcome to Omni Hub."


@mcp.tool()
def word_count(text: str) -> str:
    """Count the number of words in a text string.

    Args:
        text: The text to count words in.
    """
    count = len(text.split())
    return f"Word count: {count}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### Step 3: Test standalone

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python my_tools_server.py
```

You should see a JSON response listing `greet` and `word_count`.

### Step 4: Register as a plugin

Create `backend/app/plugins/my_tools.py`:

```python
from app.models.plugin import (
    PluginManifest, PluginKind, PluginCategory, ToolSummary
)

MANIFEST = PluginManifest(
    id="my-tools",
    name="My Tools",
    description="Custom tools via MCP.",
    version="0.1.0",
    author="Your Name",
    category=PluginCategory.OTHER,
    kind=PluginKind.MCP_STDIO,
    command="python",
    args=["scripts/my_tools_server.py"],   # relative to backend/
    tools_summary=[
        ToolSummary(name="greet", description="Say hello"),
        ToolSummary(name="word_count", description="Count words"),
    ],
)
```

Restart the server — your tools are now available to the agent.

---

## FastMCP Tool Patterns

### Basic tool

```python
@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers together."""
    return f"{a + b}"
```

### Async tool (for API calls)

```python
import httpx

@mcp.tool()
async def fetch_webpage_title(url: str) -> str:
    """Fetch the title of a webpage.

    Args:
        url: The URL to fetch.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        # Simple title extraction
        start = resp.text.find("<title>") + 7
        end = resp.text.find("</title>")
        return resp.text[start:end] if start > 6 else "No title found"
```

### Tool with complex return

```python
import json

@mcp.tool()
def analyse_csv(csv_text: str) -> str:
    """Analyse CSV data and return statistics.

    Args:
        csv_text: Raw CSV content as a string.
    """
    lines = csv_text.strip().split("\n")
    return json.dumps({
        "rows": len(lines) - 1,
        "columns": len(lines[0].split(",")) if lines else 0,
        "headers": lines[0].split(",") if lines else [],
    })
```

---

## Plugin Manifest Fields for MCP Servers

### MCP_STDIO (subprocess)

```python
PluginManifest(
    id="my-server",
    kind=PluginKind.MCP_STDIO,
    command="python",                     # executable to run
    args=["scripts/my_server.py"],        # arguments
    env_keys=["MY_API_KEY"],              # env vars injected before spawn
    requires_auth=True,                   # user must provide keys first
    lazy=True,                            # load only when user enables
)
```

### MCP_HTTP (remote server)

```python
PluginManifest(
    id="remote-tools",
    kind=PluginKind.MCP_HTTP,
    url="https://my-mcp-server.example.com/mcp",  # SSE endpoint
    env_keys=["REMOTE_API_KEY"],
    requires_auth=True,
)
```

---

## Reference Server

See the complete working example at `backend/scripts/local_mcp_server.py`:

```python
"""Local test MCP server — proper MCP protocol via FastMCP.

Provides tools for testing MCP integration with ADK's McpToolset:
  - echo: Echo back a message
  - get_server_time: Return current UTC time
  - calculate: Basic arithmetic
"""
from datetime import datetime, timezone
from mcp.server import FastMCP

mcp = FastMCP("local-test-mcp")

@mcp.tool()
def echo(message: str) -> str:
    """Echo back a message — useful for testing MCP connectivity."""
    return f"Echo: {message}"

@mcp.tool()
def get_server_time() -> str:
    """Get the current server time in UTC."""
    return f"Current server time: {datetime.now(timezone.utc).isoformat()}"

@mcp.tool()
def calculate(operation: str, a: float, b: float) -> str:
    """Perform basic arithmetic (add, subtract, multiply, divide)."""
    ops = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else "Error: division by zero",
    }
    result = ops.get(operation, f"Unknown operation: {operation}")
    return f"{a} {operation} {b} = {result}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## How the Backend Connects

The `PluginRegistry` uses ADK's `McpToolset` to connect:

```
PluginRegistry.connect_plugin("my-tools")
    └─► McpToolset(connection_params=StdioConnectionParams(
            command="python",
            args=["scripts/my_tools_server.py"]
        ))
    └─► tools = await toolset.get_tools()
    └─► Registers tools in ToolRegistry (T2 tier)
```

Your MCP server runs as a child process. The backend calls MCP's `tools/list` then `tools/call` over stdio.

---

## Built-in MCP Plugins (Already Registered)

The following MCP servers are pre-registered. Use them as examples or extend them:

| Plugin ID | Kind | Source |
|-----------|------|--------|
| `e2b-sandbox` | MCP_STDIO | `npx -y @anthropic/e2b-mcp-server` |
| `wikipedia` | MCP_STDIO | `npx -y wikipedia-mcp-server` |
| `filesystem` | MCP_STDIO | `npx -y @anthropic/mcp-filesystem` |
| `brave-search` | MCP_STDIO | `npx -y @anthropic/mcp-brave-search` |
| `github` | MCP_STDIO | `npx -y @anthropic/mcp-github` |
| `playwright` | MCP_STDIO | `npx -y @anthropic/mcp-playwright` |
| `notion` | MCP_STDIO | `npx -y @anthropic/mcp-notion` |
| `slack` | MCP_STDIO | `npx -y @anthropic/mcp-slack` |

---

## Testing with ADK Directly

You can test your MCP server without the Omni Hub backend:

```python
# test_my_server.py
import asyncio
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams

async def main():
    toolset = McpToolset(connection_params=StdioConnectionParams(
        command="python",
        args=["scripts/my_tools_server.py"]
    ))
    tools = await toolset.get_tools()
    for t in tools:
        decl = t._get_declaration()
        print(f"  {decl.name}: {decl.description}")
    await toolset.close()

asyncio.run(main())
```

---

## Best Practices

| Practice | Why |
|----------|-----|
| Return `str` from every tool | MCP spec expects string results |
| Write clear docstrings with `Args:` | The LLM reads these to decide when/how to call the tool |
| Type-annotate all parameters | MCP uses annotations to build the JSON schema |
| Keep tools focused — one action each | Better for LLM tool selection |
| Handle errors gracefully (return error strings) | Don't let exceptions crash the process |
| Use async for I/O-bound operations | Keeps the event loop responsive |

---

## FAQ

**Q: Can I use Node.js / Go / Rust instead of Python?**
A: Yes. Any language with an MCP SDK works. Set `command` to your executable (e.g. `"node"`, `"npx"`).

**Q: How do I pass API keys to my MCP server?**
A: Add key names to `env_keys` in your manifest. The backend injects them as environment variables before spawning.

**Q: My server works standalone but not as a plugin?**
A: Check that `command` and `args` paths are correct relative to `backend/`. Run `uv run python scripts/your_server.py` to verify.

**Q: Can my MCP server access the internet?**
A: Yes — it's a regular process. Use any HTTP library. For production, consider rate limiting and timeout guards.

**Q: How do I add resources (not just tools)?**
A: FastMCP supports `@mcp.resource()` — ADK doesn't consume resources yet, but the protocol supports them for future use.
