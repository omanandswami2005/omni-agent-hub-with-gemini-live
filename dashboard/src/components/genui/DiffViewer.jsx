/**
 * GenUI: DiffViewer — Side-by-side or unified diff display.
 */

export default function DiffViewer({ before = '', after = '', language = 'text' }) {
  return (
    <div className="grid grid-cols-2 gap-2 rounded-lg border border-border text-sm">
      <div className="border-r border-border p-4">
        <p className="mb-2 text-xs text-muted-foreground">Before</p>
        <pre className="overflow-x-auto">{before}</pre>
      </div>
      <div className="p-4">
        <p className="mb-2 text-xs text-muted-foreground">After</p>
        <pre className="overflow-x-auto">{after}</pre>
      </div>
    </div>
  );
}
