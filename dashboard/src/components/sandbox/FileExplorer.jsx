/**
 * Sandbox: FileExplorer — File tree for sandbox filesystem.
 */

export default function FileExplorer({ files = [], onSelect }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="border-b border-border px-4 py-2 text-xs font-medium">Files</div>
      <div className="max-h-64 overflow-y-auto p-2">
        {files.map((file, i) => (
          <button
            key={i}
            onClick={() => onSelect?.(file)}
            className="flex w-full items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted"
          >
            <span>{file.isDir ? '📁' : '📄'}</span>
            <span>{file.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
