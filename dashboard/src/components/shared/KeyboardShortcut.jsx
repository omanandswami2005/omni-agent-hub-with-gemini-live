/**
 * Shared: KeyboardShortcut — Visual keyboard shortcut indicator.
 */

export default function KeyboardShortcut({ keys = [] }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {keys.map((key, i) => (
        <kbd
          key={i}
          className="rounded border border-border bg-muted px-1.5 py-0.5 text-xs font-mono text-muted-foreground"
        >
          {key}
        </kbd>
      ))}
    </span>
  );
}
