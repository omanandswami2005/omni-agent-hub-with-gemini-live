/**
 * Sandbox: CodeEditor — Code editor for sandbox input.
 */

// TODO: Implement with Monaco Editor or CodeMirror

export default function CodeEditor({ code = '', language = 'python', onChange, readOnly = false }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted-foreground">
        <span>{language}</span>
      </div>
      <textarea
        value={code}
        onChange={(e) => onChange?.(e.target.value)}
        readOnly={readOnly}
        className="h-48 w-full resize-none bg-background p-4 font-mono text-sm focus:outline-none"
        spellCheck={false}
      />
    </div>
  );
}
