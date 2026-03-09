/**
 * Shared: EmptyState — Placeholder for empty lists/data.
 */

export default function EmptyState({ icon = '📭', title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center">
      <span className="text-4xl">{icon}</span>
      <h3 className="mt-4 text-lg font-medium">{title}</h3>
      {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
