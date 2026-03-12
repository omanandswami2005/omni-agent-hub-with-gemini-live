# Track 1: Plugin Developer Guide

> **Scope**: Create native Python plugins that give the agent new capabilities.
> **Files you touch**: Only `backend/app/plugins/your_plugin.py`
> **Time to first plugin**: ~30 minutes
> **Prerequisites**: Python, basic async knowledge

---

## Quick Start — Your First Plugin in 5 Minutes

### Step 1: Copy the template

```bash
cd backend/app/plugins
cp TEMPLATE.py weather_lookup.py
```

### Step 2: Edit the manifest

Open `weather_lookup.py` and replace the `MANIFEST`:

```python
from app.models.plugin import PluginManifest, PluginKind, PluginCategory, ToolSummary

MANIFEST = PluginManifest(
    id="weather-lookup",                     # unique slug (used in API calls)
    name="Weather Lookup",                   # display name in dashboard
    description="Get weather for any city.", # shown in plugin catalog
    version="0.1.0",
    author="Your Name",
    category=PluginCategory.OTHER,
    kind=PluginKind.NATIVE,
    icon="cloud-sun",
    module="app.plugins.weather_lookup",     # dotted import path to THIS file
    factory="get_tools",                     # function name that returns tools
    tools_summary=[
        ToolSummary(name="get_weather", description="Get current weather for a city"),
    ],
)
```

### Step 3: Implement your tool

```python
async def get_weather(city: str) -> dict:
    """Get the current weather for a city.

    Args:
        city: City name (e.g. "London", "Tokyo", "New York").

    Returns:
        A dict with temperature, conditions, and humidity.
    """
    # Your logic here — call an API, scrape a page, compute something
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://wttr.in/{city}?format=j1")
        data = resp.json()
    current = data["current_condition"][0]
    return {
        "city": city,
        "temp_c": current["temp_C"],
        "condition": current["weatherDesc"][0]["value"],
        "humidity": current["humidity"],
    }
```

### Step 4: Wire the factory

```python
from google.adk.tools import FunctionTool

def get_tools() -> list[FunctionTool]:
    return [FunctionTool(get_weather)]
```

### Step 5: Restart and test

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

Your plugin appears in the catalog automatically:
```
GET http://localhost:8000/api/v1/plugins/catalog
```

Enable it:
```
POST http://localhost:8000/api/v1/plugins/toggle
{"plugin_id": "weather-lookup", "enabled": true}
```

Now the agent can call `get_weather("Tokyo")` when users ask about the weather.

---

## Plugin Manifest — Full Reference

```python
class PluginManifest(BaseModel):
    id: str                              # Unique slug — e.g. "weather-lookup"
    name: str                            # Display name — "Weather Lookup"
    description: str                     # One-line catalog description
    version: str = "0.1.0"              # Semver
    author: str = ""                     # Your name/team
    category: PluginCategory             # SEARCH, PRODUCTIVITY, DEV, COMMUNICATION,
                                         # FINANCE, SANDBOX, DATA, CREATIVE, OTHER
    kind: PluginKind                     # NATIVE (for Python plugins)
    icon: str = ""                       # Lucide icon name (for dashboard UI)

    # ── Native plugin fields ──
    module: str                          # "app.plugins.your_file"
    factory: str = "get_tools"           # Function returning list[FunctionTool]

    # ── Behaviour ──
    lazy: bool = True                    # Load tools only when user enables
    requires_auth: bool = False          # User must provide API keys first
    env_keys: list[str] = []             # Required env var names
    tools_summary: list[ToolSummary] = []  # Pre-declared tool list
```

---

## Tool Function Contract

Every tool function MUST follow these rules:

| Rule | Why |
|------|-----|
| `async def` | ADK requires async functions |
| Type-annotated parameters | ADK uses annotations to build JSON schema for the LLM |
| Allowed types: `str`, `int`, `float`, `bool`, `list`, `dict` | ADK serialises these to Gemini function calling schema |
| Return `str` or `dict` | ADK serialises the return value as the tool result |
| Descriptive docstring | The LLM reads this to decide when/how to call the tool |
| `user_id: str` parameter (optional) | ADK auto-injects the authenticated user ID if present |

### Good Example

```python
async def search_notes(
    query: str,
    max_results: int = 5,
    user_id: str = "",   # auto-injected by ADK
) -> dict:
    """Search the user's saved notes by keyword.

    Args:
        query: Search keywords.
        max_results: Maximum number of notes to return (1-20).

    Returns:
        A dict with matching notes and total count.
    """
    # ... implementation ...
    return {"notes": [...], "total": 12}
```

### Bad Example

```python
def search(q):  # ❌ Not async, no types, no docstring, vague name
    return "result"
```

---

## Plugin with API Keys (requires_auth)

If your plugin needs API credentials:

```python
MANIFEST = PluginManifest(
    id="openweather",
    name="OpenWeather",
    description="Weather data from OpenWeather API.",
    kind=PluginKind.NATIVE,
    module="app.plugins.openweather",
    requires_auth=True,                    # Dashboard shows "API key required"
    env_keys=["OPENWEATHER_API_KEY"],      # These must be provided
    # ...
)
```

Users provide secrets through the dashboard, which calls:
```
POST /api/v1/plugins/secrets
{"plugin_id": "openweather", "secrets": {"OPENWEATHER_API_KEY": "abc123"}}
```

Access the key in your tool via environment variables — the registry injects them before connecting.

---

## Testing Your Plugin

### Unit test pattern

Create `backend/tests/test_services/test_your_plugin.py`:

```python
import pytest

class TestWeatherPlugin:
    def test_manifest_discovered(self):
        """Plugin manifest should be auto-discovered."""
        from app.services.plugin_registry import PluginRegistry
        reg = PluginRegistry()
        assert "weather-lookup" in reg._catalog

    @pytest.mark.asyncio
    async def test_get_weather_returns_dict(self):
        """Tool should return a dict with expected keys."""
        from app.plugins.weather_lookup import get_weather
        result = await get_weather("London")
        assert "city" in result
        assert "temp_c" in result

    @pytest.mark.asyncio
    async def test_get_weather_invalid_city(self):
        """Tool should handle invalid input gracefully."""
        from app.plugins.weather_lookup import get_weather
        result = await get_weather("")
        assert "error" in result or "city" in result
```

### Run tests

```bash
cd backend
python -m pytest tests/test_services/test_your_plugin.py -v
```

---

## File Structure

```
backend/app/plugins/
├── __init__.py              # Auto-discovery docs
├── TEMPLATE.py              # Copy this to start (excluded from discovery)
├── notification_sender.py   # Working example — read this first
└── weather_lookup.py        # YOUR new plugin
```

---

## Reference Examples

| File | What It Shows |
|------|--------------|
| `app/plugins/TEMPLATE.py` | Minimal skeleton with documented manifest |
| `app/plugins/notification_sender.py` | Full working plugin with 2 tools, multiple channels |
| `app/models/plugin.py` | Complete PluginManifest schema |

---

## FAQ

**Q: Do I need to restart the server?**
A: Yes — plugins are discovered at startup. Hot-reload (`--reload`) handles this during dev.

**Q: Can my plugin call other services?**
A: Yes — use `httpx`, `aiohttp`, or any async Python library. Add dependencies to `pyproject.toml`.

**Q: Can my plugin call other plugins?**
A: Not directly. If you need cross-plugin communication, use shared services or the EventBus.

**Q: What if my plugin crashes?**
A: Plugin load failures are caught and logged as warnings. Other plugins continue working. Your plugin will show `state: error` in the catalog.

**Q: Can I access the database?**
A: Yes — import Firestore client from `app.services.session_service` or create your own. Keep it async.
