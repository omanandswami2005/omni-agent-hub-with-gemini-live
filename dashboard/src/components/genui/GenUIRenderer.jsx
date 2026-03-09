/**
 * GenUI: GenUIRenderer — Dynamic renderer for server-pushed UI components.
 */

// TODO: Implement:
//   - Parse component type from server message
//   - Render appropriate component (chart, table, card, code, image, etc.)
//   - Fallback to MarkdownRenderer for unknown types

const COMPONENT_MAP = {
  chart: 'DynamicChart',
  table: 'DataTable',
  card: 'InfoCard',
  code: 'CodeBlock',
  image: 'ImageGallery',
  timeline: 'TimelineView',
  markdown: 'MarkdownRenderer',
  diff: 'DiffViewer',
  weather: 'WeatherWidget',
  map: 'MapView',
};

export default function GenUIRenderer({ type, data }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs text-muted-foreground">GenUI: {type}</p>
      <pre className="mt-2 text-sm">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
