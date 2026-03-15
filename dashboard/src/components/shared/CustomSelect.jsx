/**
 * Shared: CustomSelect — Styled dropdown replacement for native <select>.
 * Consistent with the pitch-black monochrome theme.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import { cn } from '@/lib/cn';

export default function CustomSelect({
    value,
    options = [],
    onChange,
    placeholder = 'Select…',
    className,
    labelKey = 'label',
    valueKey = 'value',
    renderOption,
}) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    const selected = options.find((o) =>
        typeof o === 'string' ? o === value : o[valueKey] === value,
    );

    const getLabel = (opt) => {
        if (typeof opt === 'string') return opt;
        return opt[labelKey] || opt[valueKey];
    };

    const getValue = (opt) => {
        if (typeof opt === 'string') return opt;
        return opt[valueKey];
    };

    const handleSelect = useCallback(
        (opt) => {
            onChange?.(getValue(opt));
            setOpen(false);
        },
        [onChange],
    );

    // Close on outside click
    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    // Close on escape
    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (e.key === 'Escape') setOpen(false);
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [open]);

    return (
        <div ref={ref} className={cn('relative', className)}>
            {/* Trigger */}
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className={cn(
                    'flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs transition-colors',
                    'border-white/[0.08] bg-white/[0.03] text-foreground',
                    'hover:bg-white/[0.06] focus:outline-none focus:ring-1 focus:ring-white/[0.15]',
                    open && 'ring-1 ring-white/[0.15]',
                )}
            >
                <span className={cn(!selected && 'text-muted-foreground')}>
                    {selected ? getLabel(selected) : placeholder}
                </span>
                <ChevronDown
                    size={14}
                    className={cn(
                        'text-muted-foreground transition-transform duration-200',
                        open && 'rotate-180',
                    )}
                />
            </button>

            {/* Dropdown */}
            {open && (
                <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-60 overflow-y-auto rounded-xl border border-white/[0.08] bg-card shadow-2xl backdrop-blur-xl animate-[scale-in_0.15s_ease-out]">
                    {options.map((opt) => {
                        const optValue = getValue(opt);
                        const isSelected = optValue === value;

                        return (
                            <button
                                key={optValue}
                                type="button"
                                onClick={() => handleSelect(opt)}
                                className={cn(
                                    'flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors',
                                    isSelected
                                        ? 'bg-white/[0.06] text-foreground'
                                        : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
                                )}
                            >
                                <span className="flex-1 text-left">
                                    {renderOption ? renderOption(opt) : getLabel(opt)}
                                </span>
                                {isSelected && <Check size={12} className="text-foreground shrink-0" />}
                            </button>
                        );
                    })}
                    {options.length === 0 && (
                        <div className="px-3 py-4 text-center text-xs text-muted-foreground">
                            No options available
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
