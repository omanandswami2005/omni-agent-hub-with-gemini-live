/**
 * HumanInputCard — In-chat card for human-in-the-loop input requests.
 *
 * Renders different input types:
 *   - confirmation: Yes/No buttons
 *   - choice: Multiple choice buttons
 *   - text: Text input with submit
 */

import { useState, useCallback } from 'react';
import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import { useTaskStore } from '@/stores/taskStore';
import { MessageSquare, CheckCircle, Send } from 'lucide-react';

export default function HumanInputCard({ input, taskId }) {
    const [textValue, setTextValue] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);

    const handleSubmit = useCallback(async (response) => {
        setSubmitting(true);
        try {
            const effectiveTaskId = taskId || input.taskId || '';
            if (effectiveTaskId) {
                await api.post(`/tasks/${effectiveTaskId}/input/${input.id}`, { input_id: input.id, response });
            }
            useTaskStore.getState().removePendingInput(input.id);
            setSubmitted(true);
        } catch (err) {
            console.error('Failed to submit input:', err);
        } finally {
            setSubmitting(false);
        }
    }, [input.id, taskId, input.taskId]);

    if (submitted) {
        return (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 dark:bg-green-500/10 border border-green-200 dark:border-green-500/20">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm text-green-700 dark:text-green-400">Response submitted</span>
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3 space-y-2">
            {/* Header */}
            <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-medium text-amber-700 dark:text-amber-400">Input Required</span>
            </div>

            {/* Prompt */}
            <p className="text-sm">{input.prompt}</p>

            {/* Input type: Confirmation (Yes/No) */}
            {input.input_type === 'confirmation' && (
                <div className="flex gap-2">
                    <button
                        onClick={() => handleSubmit('yes')}
                        disabled={submitting}
                        className="flex-1 text-xs px-3 py-2 rounded-md bg-green-500 text-white hover:bg-green-600 disabled:opacity-50"
                    >
                        Yes
                    </button>
                    <button
                        onClick={() => handleSubmit('no')}
                        disabled={submitting}
                        className="flex-1 text-xs px-3 py-2 rounded-md bg-red-500/10 text-red-500 hover:bg-red-500/20 disabled:opacity-50"
                    >
                        No
                    </button>
                </div>
            )}

            {/* Input type: Choice (Multiple choice) */}
            {input.input_type === 'choice' && (
                <div className="space-y-1.5">
                    {(input.options || []).map((option, i) => (
                        <button
                            key={i}
                            onClick={() => handleSubmit(option)}
                            disabled={submitting}
                            className={cn(
                                'w-full text-left text-sm px-3 py-2 rounded-md border',
                                'border-amber-200 dark:border-amber-500/30',
                                'hover:bg-amber-100 dark:hover:bg-amber-500/20',
                                'disabled:opacity-50 transition-colors',
                            )}
                        >
                            {option}
                        </button>
                    ))}
                </div>
            )}

            {/* Input type: Text (Free-form) */}
            {input.input_type === 'text' && (
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={textValue}
                        onChange={(e) => setTextValue(e.target.value)}
                        placeholder="Type your response..."
                        disabled={submitting}
                        className={cn(
                            'flex-1 text-sm px-3 py-2 rounded-md border',
                            'border-amber-200 dark:border-amber-500/30',
                            'bg-white dark:bg-background',
                            'focus:outline-none focus:ring-1 focus:ring-amber-500',
                            'disabled:opacity-50',
                        )}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && textValue.trim()) {
                                handleSubmit(textValue.trim());
                            }
                        }}
                    />
                    <button
                        onClick={() => textValue.trim() && handleSubmit(textValue.trim())}
                        disabled={submitting || !textValue.trim()}
                        className="px-3 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                    >
                        <Send className="h-4 w-4" />
                    </button>
                </div>
            )}
        </div>
    );
}
