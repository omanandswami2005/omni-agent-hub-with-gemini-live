/**
 * MCP: MCPCategoryNav — Category filter for MCP store.
 */

const CATEGORIES = ['All', 'Productivity', 'Development', 'Communication', 'Data', 'Creative', 'System'];

export default function MCPCategoryNav({ active = 'All', onChange }) {
  return (
    <nav className="flex gap-2 overflow-x-auto pb-2">
      {CATEGORIES.map((cat) => (
        <button
          key={cat}
          onClick={() => onChange?.(cat)}
          className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm ${
            active === cat ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'
          }`}
        >
          {cat}
        </button>
      ))}
    </nav>
  );
}
