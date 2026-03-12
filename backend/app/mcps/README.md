# MCP Server Configs

Drop a `.json` file here to register an MCP server in the Omni plugin catalog.
The `PluginRegistry` auto-discovers these at startup — **no code changes needed**.

## Quick Start

```bash
# 1. Copy the template
cp TEMPLATE.json my-mcp-server.json

# 2. Edit the fields (id, name, command, args, tags, …)

# 3. Restart the backend — it appears in the plugin catalog automatically
```

## JSON Schema

| Field | Required | Description |
|---|---|---|
| `id` | ✅ | Unique slug (must match filename minus `.json`) |
| `name` | ✅ | Display name in the catalog UI |
| `description` | ✅ | Short description |
| `kind` | ✅ | `"mcp_stdio"`, `"mcp_http"`, or `"mcp_oauth"` |
| `category` | | Plugin category: `search`, `dev`, `productivity`, `communication`, `finance`, `sandbox`, `data`, `creative`, `knowledge`, `other` |
| `command` | ✅ (stdio) | Executable: `npx`, `uvx`, `python`, `node`, `docker`, etc. |
| `args` | | Command arguments (array of strings) |
| `url` | ✅ (http/oauth) | StreamableHTTP endpoint URL |
| `oauth` | (oauth) | OAuth config: `{"client_name": "Omni Hub", "scopes": [], "redirect_uri": ""}` |
| `env` | | Default env vars as `{key: value}` |
| `env_keys` | | Required env var names (resolved from user secrets → .env → defaults) |
| `requires_auth` | | `true` if user must provide credentials |
| `tags` | | Capability tags for persona matching: `search`, `web`, `code_execution`, `sandbox`, `knowledge`, `communication`, `creative`, `media`, `data`, `device`, `*` |
| `icon` | | Icon name for the UI |
| `version` | | Semver string |
| `author` | | Author name |
| `tools_summary` | | Pre-declare tools: `[{"name": "...", "description": "..."}]` |
| `lazy` | | Default `true`. Set `false` to load tools at startup |
| `singleton` | | Default `false`. Set `true` to share one instance across users |
| `max_context_tokens` | | Max tokens per turn. `0` = no limit |

## Examples

### Stdio MCP (npx)
```json
{
  "id": "brave-search",
  "name": "Brave Search",
  "description": "Web search via the Brave Search API.",
  "kind": "mcp_stdio",
  "category": "search",
  "command": "npx",
  "args": ["-y", "@anthropic/mcp-brave-search"],
  "env_keys": ["BRAVE_API_KEY"],
  "requires_auth": true,
  "tags": ["search", "web"],
  "icon": "brave"
}
```

### Stdio MCP (uvx — Python MCP server)
```json
{
  "id": "my-python-mcp",
  "name": "My Python MCP",
  "description": "A custom Python MCP server.",
  "kind": "mcp_stdio",
  "category": "dev",
  "command": "uvx",
  "args": ["my-mcp-package"],
  "tags": ["code_execution"],
  "icon": "python"
}
```

### HTTP MCP (remote server)
```json
{
  "id": "remote-api",
  "name": "Remote API Server",
  "description": "Connects to a remote MCP server over HTTP.",
  "kind": "mcp_http",
  "category": "other",
  "url": "https://my-mcp-server.example.com/mcp",
  "tags": ["web", "data"]
}
```

### Docker MCP
```json
{
  "id": "postgres-mcp",
  "name": "PostgreSQL",
  "description": "Query PostgreSQL databases.",
  "kind": "mcp_stdio",
  "category": "data",
  "command": "docker",
  "args": ["run", "-i", "--rm", "mcp/postgres", "--connection-string", "postgresql://localhost/mydb"],
  "tags": ["data"],
  "icon": "database"
}
```

### OAuth MCP (remote server with OAuth 2.0)
```json
{
  "id": "notion",
  "name": "Notion",
  "description": "Read and write Notion pages and databases via the official Notion MCP.",
  "kind": "mcp_oauth",
  "category": "productivity",
  "url": "https://mcp.notion.com/mcp",
  "oauth": {
    "client_name": "Omni Hub",
    "scopes": [],
    "redirect_uri": ""
  },
  "requires_auth": true,
  "tags": ["knowledge", "communication"],
  "icon": "notion"
}
```
When a user clicks **Connect with OAuth** in the UI, the backend:
1. Discovers the server's OAuth endpoints via RFC 9470 + RFC 8414
2. Dynamically registers a client (RFC 7591) if needed
3. Redirects the user to the provider's authorization page (PKCE S256)
4. Exchanges the authorization code for tokens
5. Injects the Bearer token into `StreamableHTTPConnectionParams.headers`

**Alternative — static API keys**: If the remote server accepts static API keys instead of OAuth, use `kind: "mcp_http"` with `env_keys` and `requires_auth: true`. The user provides credentials through the dashboard secrets UI.
