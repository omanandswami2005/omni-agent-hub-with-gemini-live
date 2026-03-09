/**
 * GenUI: MarkdownRenderer — Render markdown content from agent responses.
 */

// TODO: Use react-markdown with rehype-highlight and remark-gfm

export default function MarkdownRenderer({ content = '' }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none">
      {/* Replace with <ReactMarkdown>{content}</ReactMarkdown> */}
      <p>{content}</p>
    </div>
  );
}
