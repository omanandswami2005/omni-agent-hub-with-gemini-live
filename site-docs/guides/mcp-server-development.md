# MCP Server Development

Guide for building MCP (Model Context Protocol) servers that integrate with Omni.

## Supported Transports

- **STDIO** — Server runs as a subprocess, communicates via stdin/stdout
- **Streamable HTTP** — Server runs as a remote HTTP service
- **OAuth** — HTTP with OAuth2 authorization flow

## Server Manifest Schema

```json
{
  "id": "unique-id",
  "name": "Display Name",
  "description": "What this plugin does",
  "kind": "MCP_STDIO | MCP_HTTP | MCP_OAUTH",
  "command": "python",
  "args": ["-m", "module"],
  "env": {"API_KEY": "required"},
  "category": "search | productivity | development | utilities",
  "singleton": false,
  "default_enabled": false,
  "tools": ["tool_name"],
  "secrets": ["API_KEY"]
}
```

## Best Practices

1. **Keep tools focused** — One tool per action, clear name and description
2. **Use JSON Schema** — Strict input validation with descriptive parameter docs
3. **Handle errors gracefully** — Return informative error messages, don't crash
4. **Document secrets** — List all required environment variables in the manifest
5. **Mark read-only servers as singleton** — Reduces resource usage for shared tools
