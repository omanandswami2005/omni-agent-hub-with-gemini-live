/**
 * GenUI: CodeBlock — Syntax-highlighted code display with copy button.
 */

// TODO: Use shiki or highlight.js for syntax highlighting

export default function CodeBlock({ code = '', language = 'text', filename = '' }) {
    return (
        <div className="rounded-lg border border-border bg-muted">
            {filename && (
                <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted-foreground">
                    <span>{filename}</span>
                    <span>{language}</span>
                </div>
            )}
            <pre className="overflow-x-auto p-4 text-sm">
                <code>{code}</code>
            </pre>
        </div>
    );
}
