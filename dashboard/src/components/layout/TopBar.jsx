/**
 * Layout: TopBar — Top navigation bar with search, user menu, theme toggle.
 */

// TODO: Implement:
//   - Command palette trigger (Ctrl+K)
//   - UserMenu (avatar + dropdown)
//   - ThemeToggle
//   - Client connection status dots
//   - Mobile hamburger menu

export default function TopBar() {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border px-4">
      <div>{/* Search / command palette trigger */}</div>
      <div className="flex items-center gap-2">{/* ThemeToggle, UserMenu */}</div>
    </header>
  );
}
