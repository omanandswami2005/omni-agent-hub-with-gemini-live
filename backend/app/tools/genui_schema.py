"""GenUI schema tool — on-demand schema retrieval for the Pixel agent.

Instead of stuffing ~1.5K tokens of JSON examples into the system prompt,
the genui agent calls ``get_genui_schema(component_type)`` to fetch the
exact schema it needs right before generating.  This saves context on
every turn where GenUI isn't being produced.
"""

from __future__ import annotations

from google.adk.tools import FunctionTool

_SCHEMAS: dict[str, dict] = {
    "chart": {
        "genui_type": "chart",
        "required": ["chartType", "data"],
        "optional": ["config"],
        "example": {
            "genui_type": "chart",
            "chartType": "bar",
            "data": [{"month": "Jan", "sales": 100}, {"month": "Feb", "sales": 150}],
            "config": {"title": "Monthly Sales", "xKey": "month", "yKeys": ["sales"]},
        },
    },
    "table": {
        "genui_type": "table",
        "required": ["columns", "rows"],
        "optional": ["title"],
        "example": {
            "genui_type": "table",
            "columns": ["Name", "Role", "Status"],
            "rows": [{"Name": "Alice", "Role": "Eng", "Status": "Active"}],
            "title": "Team",
        },
    },
    "card": {
        "genui_type": "card",
        "required": ["title"],
        "optional": ["description", "icon"],
        "example": {
            "genui_type": "card",
            "title": "Project Alpha",
            "description": "On track for Q2 launch",
            "icon": "🚀",
        },
    },
    "code": {
        "genui_type": "code",
        "required": ["code"],
        "optional": ["language", "filename"],
        "example": {
            "genui_type": "code",
            "language": "python",
            "code": "def hello():\n    print('Hello!')",
            "filename": "example.py",
        },
    },
    "image": {
        "genui_type": "image",
        "required": ["images"],
        "optional": [],
        "example": {
            "genui_type": "image",
            "images": [{"url": "https://example.com/photo.jpg", "caption": "Photo 1"}],
        },
    },
    "timeline": {
        "genui_type": "timeline",
        "required": ["events"],
        "optional": [],
        "example": {
            "genui_type": "timeline",
            "events": [{"date": "2026-01-15", "title": "Launch", "description": "v1.0 released"}],
        },
    },
    "markdown": {
        "genui_type": "markdown",
        "required": ["content"],
        "optional": [],
        "example": {"genui_type": "markdown", "content": "# Hello\nSome **bold** text"},
    },
    "diff": {
        "genui_type": "diff",
        "required": ["before", "after"],
        "optional": ["language"],
        "example": {
            "genui_type": "diff",
            "before": "old code",
            "after": "new code",
            "language": "python",
        },
    },
    "weather": {
        "genui_type": "weather",
        "required": ["location", "temp"],
        "optional": ["condition", "icon"],
        "example": {
            "genui_type": "weather",
            "location": "San Francisco",
            "temp": 72,
            "condition": "Sunny",
            "icon": "\u2600\uFE0F",
        },
    },
    "map": {
        "genui_type": "map",
        "required": ["query"],
        "optional": ["zoom"],
        "example": {"genui_type": "map", "query": "Googleplex, Mountain View, CA", "zoom": 15},
    },
}

_ALL_TYPES = ", ".join(sorted(_SCHEMAS))

# Tool name constant — used in ws_live.py to detect GenUI tool responses.
RENDER_GENUI_TOOL_NAME = "render_genui_component"


def get_genui_schema(component_type: str) -> dict:
    """Return the JSON schema and example for a GenUI component type.

    Args:
        component_type: One of: chart, table, card, code, image, timeline,
                        markdown, diff, weather, map.  Use "all" to list
                        every available type.

    Returns:
        A dict with the schema definition and a ready-to-use JSON example.
    """
    if component_type == "all":
        return {"available_types": sorted(_SCHEMAS.keys())}
    schema = _SCHEMAS.get(component_type)
    if schema is None:
        return {"error": f"Unknown type '{component_type}'. Available: {_ALL_TYPES}"}
    return schema


def render_genui_component(component_type: str, spec_json: str) -> dict:
    """Render a GenUI component that the dashboard will display.

    In live audio mode the model cannot emit text, so this tool is the
    ONLY way to produce GenUI.  Call it with the component type and a
    JSON string containing all required fields for that component type.

    Args:
        component_type: One of: chart, table, card, code, image, timeline,
                        markdown, diff, weather, map.
        spec_json: A JSON string with the component fields. Must include
                   all required fields for the chosen type (see
                   get_genui_schema for what's required).
                   Example for chart: '{"chartType":"bar","data":[{"x":"A","y":1}],"config":{"title":"My Chart"}}'

    Returns:
        A dict with ``genui_type`` set — the server intercepts this and
        sends it as a GenUI message to the dashboard.
    """
    import json as _json

    schema = _SCHEMAS.get(component_type)
    if schema is None:
        return {"error": f"Unknown component type '{component_type}'. Available: {_ALL_TYPES}"}

    try:
        spec = _json.loads(spec_json)
    except (_json.JSONDecodeError, TypeError):
        return {"error": f"Invalid JSON in spec_json: {spec_json[:200]}"}

    if not isinstance(spec, dict):
        return {"error": "spec_json must be a JSON object (dict)"}

    # Validate required fields
    missing = [f for f in schema.get("required", []) if f not in spec]
    if missing:
        return {
            "error": f"Missing required fields for '{component_type}': {missing}",
            "required": schema["required"],
            "example": schema.get("example"),
        }

    # Build the GenUI payload — genui_type is injected automatically
    spec["genui_type"] = component_type
    return {"genui_type": component_type, "rendered": True, "component": spec}


def get_genui_schema_tools() -> list[FunctionTool]:
    """Return the GenUI schema tool list."""
    return [
        FunctionTool(get_genui_schema),
        FunctionTool(render_genui_component),
    ]
