# Plugin Development Guide

This guide explains how to create custom MCP plugins for Omni.

## Plugin Types

| Type | Transport | Use Case |
|---|---|---|
| `MCP_STDIO` | Standard I/O | Local command-line tools |
| `MCP_HTTP` | Streamable HTTP | Remote API services |
| `MCP_OAUTH` | HTTP + OAuth2 | Services requiring user authentication |

## Creating an MCP STDIO Plugin

### 1. Write the MCP Server

Create a Python script that implements the MCP protocol:

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("my-plugin")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="my_tool",
            description="Does something useful",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Input query"}
                },
                "required": ["query"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "my_tool":
        result = f"Processed: {arguments['query']}"
        return [TextContent(type="text", text=result)]

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server
    asyncio.run(stdio_server(server))
```

### 2. Create the Plugin Manifest

Add a JSON manifest to `backend/app/mcps/`:

```json
{
  "id": "my-plugin",
  "name": "My Plugin",
  "description": "A custom MCP plugin",
  "kind": "MCP_STDIO",
  "command": "python",
  "args": ["-m", "my_plugin.server"],
  "env": {},
  "category": "utilities",
  "singleton": false,
  "default_enabled": false,
  "tools": ["my_tool"]
}
```

### 3. Test

Enable the plugin from the dashboard Plugin Store and invoke it via voice or text.

## Singleton Plugins

Set `"singleton": true` for stateless, read-only MCP servers (e.g., search APIs). This shares one process across all users, reducing cold-start overhead.
