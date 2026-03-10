/**
 * GenUI: CodeBlock — Code display with copy button.
 */

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

export default function CodeBlock({ code = '', language = 'text', filename = '' }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="rounded-lg border border-border bg-muted">
            <div className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted-foreground">
                <span>{filename || language}</span>
                <button
                    onClick={handleCopy}
                    className="flex items-center gap-1 hover:text-foreground"
                    aria-label="Copy code"
                >
                    {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? 'Copied' : 'Copy'}
                </button>
            </div>
            <pre className="overflow-x-auto p-4 text-sm">
                <code>{code}</code>
            </pre>
        </div>
    );
}
