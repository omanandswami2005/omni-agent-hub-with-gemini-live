# GenUI Components

GenUI (Generative UI) allows AI agents to return structured JSON that the dashboard renders as interactive React components.

## How It Works

1. Agent generates JSON with a `genui_type` field
2. Dashboard's `GenUIRenderer` looks up the component in the registry
3. The matching React component renders with the provided data

## Available Components

| Type | Description | Required Fields |
|---|---|---|
| `chart` | Interactive charts (bar, line, pie, area) | `chart_type`, `data` |
| `table` | Data tables with sorting | `headers`, `rows` |
| `card` | Info cards with icon | `title` |
| `code` | Syntax-highlighted code blocks | `code` |
| `image` | Image display with caption | `url` |
| `timeline` | Event timelines | `events` |
| `markdown` | Rich markdown content | `content` |
| `diff` | Code diff viewer | `before`, `after` |
| `weather` | Weather display cards | `location`, `temperature` |
| `map` | Interactive maps | `center`, `markers` |

## Example: Chart

```json
{
  "genui_type": "chart",
  "chart_type": "bar",
  "title": "Sales by Region",
  "data": [
    {"name": "North", "value": 4200},
    {"name": "South", "value": 3100},
    {"name": "East", "value": 5800},
    {"name": "West", "value": 2900}
  ],
  "x_key": "name",
  "y_key": "value"
}
```

## Schema Lookup Tool

The Pixel agent uses `get_genui_schema(component_type)` to fetch exact schemas before generating GenUI JSON. This tool returns required/optional fields and an example for each component type.
