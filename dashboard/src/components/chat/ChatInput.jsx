/**
 * Chat: ChatInput — Premium text input for voice interaction.
 */

import { useState } from 'react';
import { Send } from 'lucide-react';

export default function ChatInput({ onSend, disabled = false, disconnected = false }) {
    const [text, setText] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        if (text.trim() && onSend) {
            onSend(text.trim());
            setText('');
        }
    };

    return (
        <form onSubmit={handleSubmit} className="flex flex-col gap-1">
            {disconnected && (
                <p className="text-xs text-amber-500/80 px-1">Chat disconnected — reconnecting…</p>
            )}
            <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2 transition-colors focus-within:border-white/[0.15] focus-within:bg-white/[0.05]">
                <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={disconnected ? 'Reconnecting…' : 'Type a message...'}
                    disabled={disabled}
                    className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                />
                <button
                    type="submit"
                    disabled={disabled || !text.trim()}
                    className="flex h-8 w-8 items-center justify-center rounded-lg bg-foreground text-background transition-all hover:bg-foreground/90 disabled:opacity-30 disabled:hover:bg-foreground"
                >
                    <Send size={14} />
                </button>
            </div>
        </form>
    );
}
