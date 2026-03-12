/**
 * Chat: ChatInput — Text input fallback for voice interaction.
 */

import { useState } from 'react';

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
                <p className="text-xs text-amber-500">Chat disconnected — reconnecting…</p>
            )}
            <div className="flex gap-2">
                <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={disconnected ? 'Reconnecting…' : 'Type a message...'}
                    disabled={disabled}
                    className="flex-1 rounded-lg border border-border bg-background px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button
                    type="submit"
                    disabled={disabled || !text.trim()}
                    className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
                >
                    Send
                </button>
            </div>
        </form>
    );
}
