/**
 * Chat: MarkdownContent — Renders markdown text with syntax-highlighted code blocks.
 *
 * Used for both regular text messages (when they contain markdown) and
 * companion cards (rich content sent alongside voice output).
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

function CodeBlock({ children, className, ...rest }) {
    const [copied, setCopied] = useState(false);
    const match = /language-(\w+)/.exec(className || '');
    const lang = match ? match[1] : '';
    const code = String(children).replace(/\n$/, '');

    const handleCopy = () => {
        navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    if (!match) {
        return <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono" {...rest}>{children}</code>;
    }

    return (
        <div className="group relative my-2 overflow-hidden rounded-lg border border-border/40">
            <div className="flex items-center justify-between bg-muted/80 px-3 py-1.5 text-xs text-muted-foreground">
                <span>{lang}</span>
                <button onClick={handleCopy} className="flex items-center gap-1 hover:text-foreground">
                    {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
                </button>
            </div>
            <SyntaxHighlighter
                style={oneDark}
                language={lang}
                PreTag="div"
                customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.8rem' }}
            >
                {code}
            </SyntaxHighlighter>
        </div>
    );
}

export default function MarkdownContent({ content }) {
    if (!content) return null;

    return (
        <div className="prose prose-sm dark:prose-invert max-w-none break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    code: CodeBlock,
                    // Style tables
                    table: ({ children }) => (
                        <div className="my-2 overflow-x-auto rounded-lg border border-border/40">
                            <table className="min-w-full text-xs">{children}</table>
                        </div>
                    ),
                    th: ({ children }) => (
                        <th className="bg-muted/60 px-3 py-1.5 text-left text-xs font-medium">{children}</th>
                    ),
                    td: ({ children }) => (
                        <td className="border-t border-border/30 px-3 py-1.5 text-xs">{children}</td>
                    ),
                    // Style links to open externally
                    a: ({ children, href }) => (
                        <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                            {children}
                        </a>
                    ),
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
}
