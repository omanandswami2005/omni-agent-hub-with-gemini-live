/**
 * Layout: Sidebar — Navigation sidebar with route links and persona quick-switch.
 */

// TODO: Implement:
//   - Nav links: Dashboard, Personas, MCP Store, Sessions, Clients, Settings
//   - Active route highlighting
//   - Collapse/expand toggle (Ctrl+/)
//   - Persona quick-switch at bottom
//   - Connection status indicator

export default function Sidebar() {
  return (
    <aside className="hidden w-64 flex-col border-r border-border bg-surface md:flex">
      <div className="p-4 font-bold text-lg">Omni</div>
      <nav className="flex-1 space-y-1 px-2">{/* Nav items */}</nav>
    </aside>
  );
}
