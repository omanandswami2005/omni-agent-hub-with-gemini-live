/**
 * GenUI: TimelineView — Vertical timeline for events/history.
 */

export default function TimelineView({ events = [] }) {
  return (
    <div className="space-y-4">
      {events.map((event, i) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="h-3 w-3 rounded-full bg-primary" />
            {i < events.length - 1 && <div className="w-0.5 flex-1 bg-border" />}
          </div>
          <div className="pb-4">
            <p className="text-sm font-medium">{event.title}</p>
            <p className="text-xs text-muted-foreground">{event.time}</p>
            {event.description && <p className="mt-1 text-sm">{event.description}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
