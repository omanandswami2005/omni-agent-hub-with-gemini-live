/**
 * GenUI: InfoCard — Rich information card with icon, title, and content.
 */

export default function InfoCard({ title, description, icon, children }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-center gap-2">
        {icon && <span className="text-xl">{icon}</span>}
        <h3 className="font-medium">{title}</h3>
      </div>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
