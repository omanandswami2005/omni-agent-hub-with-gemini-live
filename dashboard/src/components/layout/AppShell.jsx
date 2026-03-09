/**
 * Layout: AppShell — Main application shell with sidebar + content area.
 */

// TODO: Implement:
//   - Sidebar (collapsible) + TopBar + main content slot
//   - Mobile responsive with drawer navigation
//   - Keyboard shortcut overlay

export default function AppShell({ children }) {
  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* <Sidebar /> */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* <TopBar /> */}
        <main className="flex-1 overflow-y-auto p-4">{children}</main>
      </div>
    </div>
  );
}
