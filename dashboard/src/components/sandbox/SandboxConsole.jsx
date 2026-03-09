/**
 * Sandbox: SandboxConsole — Live output console for E2B sandbox execution.
 */

// TODO: Implement:
//   - Terminal-style output display
//   - Auto-scroll
//   - ANSI color code support
//   - Clear button

export default function SandboxConsole({ output = [] }) {
    return (
        <div className="rounded-lg border border-border bg-black p-4 font-mono text-sm text-green-400">
            <div className="max-h-64 overflow-y-auto">
                {output.map((line, i) => (
                    <div key={i}>{line}</div>
                ))}
            </div>
        </div>
    );
}
