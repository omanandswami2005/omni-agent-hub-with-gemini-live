/**
 * Sandbox: CodeEditor — Code editor with language selector and run button.
 */

import { Play } from 'lucide-react';

const LANGUAGES = ['python', 'javascript', 'bash', 'sql'];

export default function CodeEditor({ code = '', language = 'python', onChange, onRun, onLanguageChange, readOnly = false }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex gap-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang}
              onClick={() => onLanguageChange?.(lang)}
              className={`rounded px-2 py-0.5 text-xs transition-colors ${language === lang ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
                }`}
            >
              {lang}
            </button>
          ))}
        </div>
        {onRun && (
          <button
            onClick={onRun}
            className="flex items-center gap-1 rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
          >
            <Play className="h-3 w-3" />
            Run
          </button>
        )}
      </div>
      <div className="relative">
        {/* Line numbers gutter */}
        <div className="pointer-events-none absolute left-0 top-0 h-full w-10 border-r border-border bg-muted/30 p-4 font-mono text-xs text-muted-foreground">
          {code.split('\n').map((_, i) => (
            <div key={i} className="leading-5 text-right">{i + 1}</div>
          ))}
        </div>
        <textarea
          value={code}
          onChange={(e) => onChange?.(e.target.value)}
          readOnly={readOnly}
          className="h-48 w-full resize-none bg-background py-4 pl-14 pr-4 font-mono text-sm leading-5 focus:outline-none"
          spellCheck={false}
        />
      </div>
    </div>
  );
}
