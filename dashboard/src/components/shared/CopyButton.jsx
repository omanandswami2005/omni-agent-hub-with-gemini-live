/**
 * Shared: CopyButton — Click-to-copy button with feedback.
 */

import { useState } from 'react';

export default function CopyButton({ text, className = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button onClick={handleCopy} className={`text-xs text-muted-foreground hover:text-foreground ${className}`}>
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}
