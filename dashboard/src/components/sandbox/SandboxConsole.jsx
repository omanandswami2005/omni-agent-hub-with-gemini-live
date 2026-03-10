/**
 * Sandbox: SandboxConsole — Live output console for E2B sandbox execution.
 */

import { useRef, useEffect } from 'react';

export default function SandboxConsole({ output = [], onClear }) {
    const endRef = useRef(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [output]);

    return (
        <div className="relative rounded-lg border border-border bg-black">
            {onClear && output.length > 0 && (
                <button
                    onClick={onClear}
                    className="absolute right-2 top-2 rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
                >
                    Clear
                </button>
            )}
            <div className="max-h-72 overflow-y-auto p-4 font-mono text-sm">
                {output.length === 0 ? (
                    <span className="text-gray-600">No output yet…</span>
                ) : (
                    output.map((line, i) => (
                        <div
                            key={i}
                            className={line.type === 'stderr' ? 'text-red-400' : 'text-green-400'}
                        >
                            {line.text ?? line}
                        </div>
                    ))
                )}
                <div ref={endRef} />
            </div>
        </div>
    );
}
