/**
 * Component: CommandPalette — Global search/command modal (⌘K).
 */

import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router';
import { Search, X, MessageSquare, Users, FolderOpen, Settings, Zap } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';

const commands = [
    { id: 'chat', label: 'New Chat', icon: MessageSquare, path: '/' },
    { id: 'sessions', label: 'Sessions', icon: FolderOpen, path: '/sessions' },
    { id: 'personas', label: 'Personas', icon: Users, path: '/personas' },
    { id: 'plugins', label: 'Plugins', icon: Zap, path: '/plugins' },
    { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' },
];

export default function CommandPalette() {
    const navigate = useNavigate();
    const { commandPaletteOpen, setCommandPalette } = useUiStore();
    const [query, setQuery] = useState('');
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef(null);

    const filtered = commands.filter((cmd) =>
        cmd.label.toLowerCase().includes(query.toLowerCase())
    );

    // Focus input when opened
    useEffect(() => {
        if (commandPaletteOpen) {
            setTimeout(() => inputRef.current?.focus(), 50);
            setQuery('');
            setSelectedIndex(0);
        }
    }, [commandPaletteOpen]);

    // Global keyboard shortcut
    useEffect(() => {
        const handleKeyDown = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                setCommandPalette(!commandPaletteOpen);
            }
            if (e.key === 'Escape' && commandPaletteOpen) {
                setCommandPalette(false);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [commandPaletteOpen, setCommandPalette]);

    const handleSelect = (path) => {
        navigate(path);
        setCommandPalette(false);
    };

    const handleKeyDown = (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedIndex((i) => (i + 1) % filtered.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedIndex((i) => (i - 1 + filtered.length) % filtered.length);
        } else if (e.key === 'Enter' && filtered[selectedIndex]) {
            handleSelect(filtered[selectedIndex].path);
        }
    };

    if (!commandPaletteOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-24">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={() => setCommandPalette(false)}
            />

            {/* Modal */}
            <div className="relative w-full max-w-lg rounded-xl border border-border bg-background shadow-2xl">
                {/* Search input */}
                <div className="flex items-center gap-3 border-b border-border px-4 py-3">
                    <Search size={18} className="text-muted-foreground" />
                    <input
                        ref={inputRef}
                        type="text"
                        placeholder="Search commands..."
                        value={query}
                        onChange={(e) => {
                            setQuery(e.target.value);
                            setSelectedIndex(0);
                        }}
                        onKeyDown={handleKeyDown}
                        className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                    />
                    <button onClick={() => setCommandPalette(false)} className="text-muted-foreground hover:text-foreground">
                        <X size={18} />
                    </button>
                </div>

                {/* Results */}
                <div className="max-h-72 overflow-y-auto p-2">
                    {filtered.length === 0 ? (
                        <p className="p-4 text-center text-sm text-muted-foreground">No results found</p>
                    ) : (
                        filtered.map((cmd, index) => (
                            <button
                                key={cmd.id}
                                onClick={() => handleSelect(cmd.path)}
                                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${index === selectedIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
                                    }`}
                            >
                                <cmd.icon size={16} className="text-muted-foreground" />
                                <span className="text-sm">{cmd.label}</span>
                            </button>
                        ))
                    )}
                </div>

                {/* Footer hint */}
                <div className="border-t border-border px-4 py-2 text-center">
                    <span className="text-xs text-muted-foreground">Use ↑↓ to navigate, Enter to select, Esc to close</span>
                </div>
            </div>
        </div>
    );
}